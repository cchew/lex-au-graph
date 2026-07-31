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
            local_name = child.tag.split("}")[-1]
            # <heading> text (e.g. "Amendment") sits immediately before the first
            # <content>/<p> text with only whitespace between them once
            # concatenated -- without this exclusion, a heading ending in a
            # capitalized word bleeds into the citation regex's greedy
            # preceding-title-word match (e.g. "Amendment" + "The Fair Work Act
            # 2009" -> "Amendment The Fair Work Act 2009"). Headings are titles,
            # not body prose, so they are out of scope for citation extraction
            # regardless.
            child_is_excluded = local_name in ("ref", "heading")
            walk(child, skip or child_is_excluded)
            if child.tail:
                parts.append(child.tail)

    walk(section_el, False)
    # Concatenate with no separator: adjacent inline-formatting runs (e.g. a hyphen
    # split into its own <i> element, as in "Self<i>-</i><i>Government)</i>") carry
    # no whitespace between them in the source, and inserting one here would fracture
    # the word at that boundary. Any real whitespace is already present inside the
    # individual text/tail fragments; .split()/" ".join() below just normalizes runs.
    return " ".join("".join(parts).split())


_SECTION_NUM = r"\d+[A-Z]*(?:\([a-zA-Z0-9]+\))*"
_INTRA_ACT_PATTERN = re.compile(
    r"\b(?:[Ss]ubsections?|[Ss]ections?|s)\s+"
    + _SECTION_NUM +
    r"(?:\s*(?:,|and|to)\s*" + _SECTION_NUM + r")*"
)
_SECTION_NUM_PATTERN = re.compile(r"\d+[A-Z]*")
_SECTION_NUM_TOKEN_PATTERN = re.compile(_SECTION_NUM)


def extract_intra_act_citations(section_el: ET._Element) -> list[str]:
    """Regex-match bare intra-Act section references ('section 26WD', 's 26WD',
    'sections 26WD and 26WE', 'subsection 26WD(2)') over section text, excluding
    text inside existing <ref> elements. Bare references with no section number
    ('subsection (2)', 'this Division') are excluded by design — they identify
    the current section/container, not a distinct target node (see spec Scope
    decisions). Duplicate mentions are NOT deduped, matching extract_prose_citations.
    """
    text = _text_outside_refs(section_el)
    return _INTRA_ACT_PATTERN.findall(text)


def extract_section_numbers(match: str) -> list[str]:
    """Pull every section number/letter suffix out of a raw intra-Act match, for
    multi-section list citations (e.g. 'sections 26WD and 26WE' -> ['26WD', '26WE']).
    Pinpoint subsection suffixes are stripped per-token the same way
    extract_section_number strips them for the single-section case (e.g.
    's 2(32) and 6(1)' -> ['2', '6'], not ['2(32)', '6(1)']). A single-section
    match, including a pinpoint one, returns a single-element list. Returns []
    if no section number is found (should not normally occur given
    _INTRA_ACT_PATTERN's own match requirements)."""
    tokens = _SECTION_NUM_TOKEN_PATTERN.findall(match)
    return [token.split("(", 1)[0] for token in tokens]


def extract_section_number(match: str) -> Optional[str]:
    """Pull the bare section number/letter suffix out of a raw intra-Act match,
    for eId-index lookup in graph.py. For a multi-section list match (e.g.
    'sections 26WD and 26WE'), returns only the first section number — see
    plan's Design notes for the v1 scope decision on list citations.
    """
    numbers = extract_section_numbers(match)
    return numbers[0] if numbers else None
