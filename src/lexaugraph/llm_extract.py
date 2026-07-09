from __future__ import annotations
import json
import re

import anthropic

# Conventional rough heuristic for English prose: ~4 characters per token. No tokenizer
# dependency needed for a conservative estimate used purely to decide whether to chunk.
_CHARS_PER_TOKEN = 4

# The original max_tokens truncation bug (79 candidate terms in one call) burned 4482 of
# the 8192 output-token budget on extended-thinking alone before ever emitting the JSON
# array. Term-count batching (_EXTRACTION_BATCH_SIZE in cli.py) bounds output-array size,
# but does nothing to bound section_text — the input most plausibly correlated with
# thinking-token consumption. This ceiling is a conservative cap on estimated input
# tokens for section_text, independent of how many candidate terms are batched per call.
_SECTION_TEXT_TOKEN_CEILING = 6000


def estimate_tokens(text: str) -> int:
    """Rough token-count estimate using the conventional ~4 chars/token heuristic for
    English prose. Not exact — used only to decide whether section_text needs chunking."""
    return len(text) // _CHARS_PER_TOKEN


def chunk_section_text(
    section_text: str,
    token_ceiling: int = _SECTION_TEXT_TOKEN_CEILING,
) -> list[str]:
    """Split section_text into chunks whose estimated token count stays under
    token_ceiling, splitting on sentence-ish boundaries so definitions aren't cut
    mid-sentence any more than necessary.

    If section_text already fits under the ceiling, returns [section_text] unchanged
    (the common case — no unnecessary extra API calls for ordinary-sized sections).

    Chunks are built by greedily accumulating sentence-like segments (split on ". "
    boundaries, since section_text is already whitespace-normalised single-line prose)
    until adding the next segment would exceed the ceiling. A single segment that alone
    exceeds the ceiling is kept whole in its own chunk rather than being force-split
    mid-word, since legal definitions must never be silently truncated mid-clause.
    """
    if estimate_tokens(section_text) <= token_ceiling:
        return [section_text]

    ceiling_chars = token_ceiling * _CHARS_PER_TOKEN
    # Split on sentence-ish boundaries, keeping the delimiter attached to each segment.
    segments = re.split(r"(?<=[.;])\s+", section_text)

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for seg in segments:
        seg_len = len(seg) + (1 if current else 0)  # account for the joining space
        if current and current_len + seg_len > ceiling_chars:
            chunks.append(" ".join(current))
            current = [seg]
            current_len = len(seg)
        else:
            current.append(seg)
            current_len += seg_len
    if current:
        chunks.append(" ".join(current))
    return chunks


_SYSTEM_PROMPT = (
    "You extract legal defined-term definitions from Australian Commonwealth legislation section text. "
    "For each candidate term given, find its definition within the section text and return the FULL "
    "definition text as an EXACT VERBATIM SUBSTRING of the provided section text — do not paraphrase, "
    "summarise, or alter wording, spacing, or punctuation in any way. If a candidate term's definition "
    "cannot be found verbatim in the section text, omit it from the output. "
    "Return ONLY valid JSON — no markdown fences, no commentary."
)


def build_extraction_prompt(section_text: str, candidate_terms: list[str]) -> str:
    terms_list = "\n".join(f"- {t}" for t in candidate_terms)
    return (
        f"## Section text\n{section_text}\n\n"
        f"## Candidate defined terms to extract\n{terms_list}\n\n"
        "## Task\n"
        "For each candidate term, extract its full definition (including any lettered sub-clauses "
        "that are part of the same definition) as an exact verbatim substring of the section text above. "
        "Return this JSON schema:\n"
        '[{"term": "...", "definition_text": "..."}, ...]'
    )


def extract_definitions_from_section(
    section_text: str,
    candidate_terms: list[str],
    client: anthropic.Anthropic,
    model: str | None = None,
) -> list[dict[str, str]]:
    """Extract verbatim definitions for candidate terms from a section's text via LLM, byte-verified
    against section_text before being returned. Anything not found verbatim is dropped, not raised."""
    if not candidate_terms:
        return []
    prompt = build_extraction_prompt(section_text, candidate_terms)
    create_kwargs = dict(
        model=model or "claude-sonnet-5",
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        response = client.messages.create(temperature=0, **create_kwargs)
    except anthropic.BadRequestError as e:
        if "temperature" in str(e):
            response = client.messages.create(**create_kwargs)
        else:
            raise
    text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    if not text_blocks:
        return []
    raw = text_blocks[0].strip()
    raw = re.sub(r"^```json\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    verified = []
    for item in data:
        if not isinstance(item, dict):
            continue
        term = item.get("term", "")
        def_text = item.get("definition_text", "")
        if term and def_text and def_text in section_text:
            verified.append({"term": term, "definition_text": def_text})
    return verified
