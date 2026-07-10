from __future__ import annotations
import re
from typing import Optional

import lxml.etree as ET

_LEADING_ARTICLE_PATTERN = re.compile(r"^(the|this|that)\s+", re.IGNORECASE)
_YEAR_PATTERN = re.compile(r"^(.+?)\s+(\d{4})$")

# "of" and "and" are the two lowercase connectors that actually appear mid-title in the
# real corpus (e.g. "Freedom of Information Act 1982", "Competition and Consumer Act 2010").
# Deliberately NOT including "the"/"in"/"for"/"on"/"to" here — those are common enough in
# ordinary prose that allowing them as connectors causes the match to swallow preceding
# unrelated capitalized words (verified empirically: "Nothing in the Fair Work Act 2009"
# over-matches to "Nothing in the Fair Work Act 2009" instead of just "Fair Work Act 2009"
# once "in"/"the" are added to the connector set).
_TITLE_CONNECTOR = r"(?:of|and)"
# Includes U+2019 (curly apostrophe) alongside the straight one: real corpus text uses
# the typographic quote in titles like "Veterans’ Entitlements Act 1986", and without it
# in this class the match breaks mid-word and drops the leading word(s) of the title.
_TITLE_WORD = r"(?:[A-Z(][\w'’&()\-]*|" + _TITLE_CONNECTOR + r")"
_CITATION_PATTERN = re.compile(
    r"\b[A-Z(][\w'’&()\-]*(?:\s+" + _TITLE_WORD + r"){0,9}\s+(?:Act|Regulations?|Rules?)\s+\d{4}\b"
)


def normalize_title(text: str) -> Optional[tuple[str, int]]:
    """Normalize a citation string to match ActNode.title.lower() index-key format.

    Strips a single leading "the"/"this"/"that", lowercases, collapses whitespace,
    normalizes curly apostrophes, and extracts the trailing year. Returns None if
    the result doesn't look like a plausible title (fewer than 3 words total
    including the year, or no year found).
    """
    normalized = " ".join(text.split()).lower()
    normalized = normalized.replace("’", "'").replace("‘", "'")
    normalized = _LEADING_ARTICLE_PATTERN.sub("", normalized)
    match = _YEAR_PATTERN.match(normalized)
    if not match:
        return None
    title_part, year_str = match.group(1), match.group(2)
    if len(title_part.split()) < 2:
        return None
    return f"{title_part} {year_str}", int(year_str)


def is_self_citation(normalized_title: str, own_title: str) -> bool:
    """True if normalized_title refers to own_title itself (a citing Act mentioning itself)."""
    own_normalized = normalize_title(own_title)
    return own_normalized is not None and own_normalized[0] == normalized_title


def extract_prose_citations(section_el: ET._Element) -> list[str]:
    """Regex-match '<Title Case Words> (Act|Regulations|Rules) <YYYY>' over section text,
    excluding text inside existing <ref> elements (already captured by the tagged-ref
    extraction pass in loader.py — re-matching it here would double-count the same
    citation). Duplicate mentions within a section are NOT deduped: each occurrence is
    returned separately so downstream mention-count aggregation in graph.py is accurate.
    """
    text = _text_outside_refs(section_el)
    return _CITATION_PATTERN.findall(text)


def _text_outside_refs(section_el: ET._Element) -> str:
    parts: list[str] = []

    def walk(el: ET._Element, skip: bool) -> None:
        if not skip and el.text:
            parts.append(el.text)
        for child in el:
            child_is_ref = child.tag.split("}")[-1] == "ref"
            walk(child, skip or child_is_ref)
            if child.tail:
                parts.append(child.tail)

    walk(section_el, False)
    return " ".join(" ".join(parts).split())
