from __future__ import annotations
import json
import re
from dataclasses import dataclass
from typing import Optional

import anthropic

from .models import RelationType

_WINDOW_CHARS = 80

_AMENDS_PATTERN = re.compile(r"\bamend\w*\b", re.IGNORECASE)
_REPEALS_PATTERN = re.compile(r"\brepeal\w*\b", re.IGNORECASE)
_REFERENCES_DEFINITION_PATTERN = re.compile(
    r"\bhas the same meaning as\b|\bas defined in\b|\bwithin the meaning of\b",
    re.IGNORECASE,
)

_RELATION_PATTERNS: dict[RelationType, re.Pattern[str]] = {
    RelationType.AMENDS: _AMENDS_PATTERN,
    RelationType.REPEALS: _REPEALS_PATTERN,
    RelationType.REFERENCES_DEFINITION: _REFERENCES_DEFINITION_PATTERN,
}


@dataclass
class RelationClassification:
    relation: RelationType
    relation_confidence: float


def classify_relation_regex(ref_text: str, section_text: str) -> Optional[RelationClassification]:
    """Verb-proximity regex classification. Scans a window of text immediately
    before and after ref_text's first occurrence in section_text -- excluding
    ref_text itself, since a citation's own title can contain a relation
    keyword (e.g. "Superannuation Amendment Act 1988") without that keyword
    describing what this citation *does*.

    Returns None when the window matches more than one relation pattern
    (ambiguous) -- the caller should fall back to LLM classification. A clean
    single match, or a clean absence of any match (defaults to CITES), both
    return a confident result here.
    """
    idx = section_text.find(ref_text)
    if idx == -1:
        return RelationClassification(relation=RelationType.CITES, relation_confidence=0.75)

    before = section_text[max(0, idx - _WINDOW_CHARS):idx]
    after_start = idx + len(ref_text)
    after = section_text[after_start:after_start + _WINDOW_CHARS]
    window = f"{before} {after}"

    matched = [rel for rel, pattern in _RELATION_PATTERNS.items() if pattern.search(window)]

    if len(matched) > 1:
        return None
    if len(matched) == 1:
        return RelationClassification(relation=matched[0], relation_confidence=0.85)
    return RelationClassification(relation=RelationType.CITES, relation_confidence=0.75)


_SYSTEM_PROMPT = (
    "You classify how one provision of Australian Commonwealth legislation refers to "
    "another. Given the citing text and its surrounding context, choose exactly one "
    "relation: \"amends\" (the citing text amends the cited provision), \"repeals\" "
    "(the citing text repeals the cited provision), \"references_definition\" (the "
    "citing text points to the cited provision for the meaning of a term), or \"cites\" "
    "(a plain citation, none of the above). Return ONLY valid JSON: "
    '{"relation": "..."} -- no markdown fences, no commentary.'
)


def build_classification_prompt(ref_text: str, section_text: str) -> str:
    return (
        f"## Citing text\n{ref_text}\n\n"
        f"## Surrounding section text\n{section_text}\n\n"
        "## Task\nClassify the relation this citation represents."
    )


def classify_relation_llm(
    ref_text: str,
    section_text: str,
    client: anthropic.Anthropic,
    model: str | None = None,
) -> RelationClassification:
    """LLM fallback for ambiguous regex results. Always returns a result --
    an unparseable or invalid LLM response defaults to CITES at low
    confidence rather than raising, since a build-time classification pass
    must not crash on one ambiguous citation."""
    prompt = build_classification_prompt(ref_text, section_text)
    create_kwargs = dict(
        model=model or "claude-sonnet-5",
        max_tokens=1024,
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
        return RelationClassification(relation=RelationType.CITES, relation_confidence=0.3)
    raw = text_blocks[0].strip()
    raw = re.sub(r"^```json\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        data = json.loads(raw)
        relation = RelationType(data["relation"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return RelationClassification(relation=RelationType.CITES, relation_confidence=0.3)
    return RelationClassification(relation=relation, relation_confidence=0.6)


def classify_relation(
    ref_text: str,
    section_text: str,
    client: Optional[anthropic.Anthropic],
    model: str | None = None,
) -> RelationClassification:
    """Hybrid entry point: regex first, LLM fallback only when the regex
    signal is ambiguous and a client is available. This is the single
    function loader.py calls for every extracted citation."""
    regex_result = classify_relation_regex(ref_text, section_text)
    if regex_result is not None:
        return regex_result
    if client is None:
        return RelationClassification(relation=RelationType.CITES, relation_confidence=0.3)
    return classify_relation_llm(ref_text, section_text, client, model=model)
