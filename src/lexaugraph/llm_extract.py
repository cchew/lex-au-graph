from __future__ import annotations
import json
import re

import anthropic

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
