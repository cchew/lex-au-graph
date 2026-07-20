from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from typing import Optional

import lxml.etree as ET

from .models import ActData, ActNode, DefinedTermNode, RefEdge, SectionNode
from . import citations

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN = f"{{{AKN_NS}}}"

_UNTAGGED_DEF_PATTERN = re.compile(r"^([a-zA-Z][a-zA-Z0-9 \-']{2,60}) means ")
_RECURRENCE_THRESHOLD = 2


def parse_act(xml_path: Path, index_entry: dict) -> ActData:
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    act_node = _parse_act_node(root, index_entry)
    sections, ref_edges = _parse_sections(root, act_node.frbr_uri)
    defined_terms = _extract_defined_terms(root, act_node.frbr_uri)

    return ActData(
        act_node=act_node,
        sections=sections,
        defined_terms=defined_terms,
        ref_edges=ref_edges,
    )


def load_corpus(corpus_dir: Path) -> list[ActData]:
    index_path = corpus_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(
            f"No index.json found in {corpus_dir}. "
            "Check the corpus path or run 'lexaugraph build --corpus-dir <path>'."
        )
    index = json.loads(index_path.read_text())
    acts_map = index.get("acts")
    if acts_map is None:
        raise ValueError(f"index.json in {corpus_dir} is missing the 'acts' key.")
    result = []
    for entry in acts_map.values():
        xml_path = corpus_dir / entry["xml_path"]
        if xml_path.exists():
            try:
                result.append(parse_act(xml_path, entry))
            except ValueError as e:
                print(f"Warning: {e} — skipping.", file=sys.stderr)
        else:
            print(f"Warning: XML not found: {xml_path}", file=sys.stderr)
    return result


def _parse_act_node(root: ET._Element, index_entry: dict) -> ActNode:
    work_uri_el = root.find(f".//{AKN}FRBRWork/{AKN}FRBRuri")
    frbr_uri = work_uri_el.get("value", "").rstrip("/") if work_uri_el is not None else ""
    if not frbr_uri:
        raise ValueError(
            f"FRBRuri missing in {index_entry.get('xml_path', '?')} — cannot build graph node."
        )

    expr_date_el = root.find(f".//{AKN}FRBRExpression/{AKN}FRBRdate")
    compilation_date: Optional[str] = None
    if expr_date_el is not None and expr_date_el.get("name") == "Generation":
        compilation_date = expr_date_el.get("date")

    return ActNode(
        frbr_uri=frbr_uri,
        title=index_entry["name"],
        year=index_entry["year"],
        compilation_date=index_entry.get("effective_date") or compilation_date,
    )


def _parse_sections(
    root: ET._Element, act_frbr_uri: str
) -> tuple[list[SectionNode], list[RefEdge]]:
    sections: list[SectionNode] = []
    ref_edges: list[RefEdge] = []

    for section in root.iter(f"{AKN}section"):
        eid = section.get("eId", "")
        heading_el = section.find(f"{AKN}heading")
        heading: Optional[str] = None
        if heading_el is not None and heading_el.text:
            heading = heading_el.text.strip()

        text = " ".join("".join(section.itertext()).split())
        provision_type = "schedule" if "schedule" in eid.lower() else "section"

        node = SectionNode(
            eid=eid,
            act_frbr_uri=act_frbr_uri,
            heading=heading,
            text=text,
            provision_type=provision_type,
        )
        sections.append(node)

        for ref_el in section.findall(f".//{AKN}ref"):
            href = ref_el.get("href") or ""
            ref_text = "".join(ref_el.itertext()).strip()
            is_cross_act = not href.startswith("#")
            ref_edges.append(RefEdge(
                source_id=node.node_id,
                ref_text=ref_text,
                is_cross_act=is_cross_act,
                target_href=href,
            ))

        for raw_match in citations.extract_prose_citations(section):
            normalized = citations.normalize_title(raw_match)
            if normalized is None:
                continue
            title, _year = normalized
            ref_edges.append(RefEdge(
                source_id=node.node_id,
                ref_text=raw_match,
                is_cross_act=True,
                target_href=None,
                matched_title=title,
            ))

        for raw_match in citations.extract_intra_act_citations(section):
            for section_number in citations.extract_section_numbers(raw_match):
                ref_edges.append(RefEdge(
                    source_id=node.node_id,
                    ref_text=raw_match,
                    is_cross_act=False,
                    target_href=None,
                    matched_title=None,
                    matched_section=section_number,
                ))

    return sections, ref_edges


def _extract_defined_terms(
    root: ET._Element, act_frbr_uri: str
) -> list[DefinedTermNode]:
    defined_terms: list[DefinedTermNode] = []
    ps = root.xpath(
        './/*[local-name()="p"]'
        '[*[local-name()="term"] and *[local-name()="def"]]'
    )
    for p in ps:
        term_el = p.find(f"{AKN}term")
        def_el = p.find(f"{AKN}def")
        term_text = (term_el.text or "").strip()
        if not term_text:
            continue
        def_text = "".join(def_el.itertext()).strip()
        section_eid = _ancestor_section_eid(p)
        defined_terms.append(DefinedTermNode(
            term=term_text.lower(),
            display_term=term_text,
            act_frbr_uri=act_frbr_uri,
            section_eid=section_eid,
            definition_text=def_text,
        ))
    return defined_terms


def _ancestor_section_eid(element: ET._Element) -> str:
    parent = element.getparent()
    while parent is not None:
        if parent.tag.split("}")[-1] == "section":
            return parent.get("eId", "")
        parent = parent.getparent()
    return ""


_INLINE_FORMATTING_TAGS = {"b", "i", "u", "sup", "sub", "span"}


def find_untagged_candidates(root: ET._Element) -> list[tuple[str, ET._Element]]:
    """Find <p> elements with no substantive child elements whose text matches an
    'X means' pattern.

    These are untagged prose definitions (no AKN <term>/<def> markup) — e.g.
    "<p>income support payment means a payment of:</p>" followed by sibling
    <paragraph> elements holding the lettered sub-clauses. Returns
    (candidate_term, the <p> element) pairs.

    Two structural shapes are matched:
      1. A fully childless <p> — match against p.text directly.
      2. A <p> whose only children are inline-formatting tags (<b>, <i>, <u>,
         <sup>, <sub>, <span> — never <term>/<def>) — match against the
         flattened itertext(). This is the shape found in the real corpus for
         terms like "income support payment", where OPC/AKN pipeline markup
         wraps the definiendum in a bold/italic span without adding semantic
         <term>/<def> tagging. Any <p> with a block-level or semantic child
         (e.g. <term>, <def>, <ul>, <blockList>) is excluded either way, since
         such a child would not be in _INLINE_FORMATTING_TAGS.
    """
    candidates = []
    for p in root.iter(f"{AKN}p"):
        if len(p) == 0:
            if not p.text:
                continue
            text = p.text.strip()
        else:
            child_tags = {c.tag.split("}")[-1] for c in p}
            if not child_tags <= _INLINE_FORMATTING_TAGS:
                continue
            text = "".join(p.itertext()).strip()
        m = _UNTAGGED_DEF_PATTERN.match(text)
        if m:
            candidates.append((m.group(1).strip(), p))
    return candidates


def filter_by_recurrence(
    candidates: list[tuple[str, ET._Element]], full_text: str
) -> list[tuple[str, ET._Element]]:
    """Keep candidates whose term recurs more than _RECURRENCE_THRESHOLD times in full_text.

    Validated empirically (see docs/research/legislation/2026-07-09-legal-definition-extraction-nlp-scan.md):
    candidates recurring more than twice elsewhere in the Act are far more likely to be genuine
    defined terms than incidental phrases matching the "X means" pattern.
    """
    kept = []
    for term, p in candidates:
        pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
        if len(pattern.findall(full_text)) > _RECURRENCE_THRESHOLD:
            kept.append((term, p))
    return kept


def _full_act_text(root: ET._Element) -> str:
    """Whitespace-normalised full text of the entire Act, for recurrence counting.

    Simplest correct approach: join root.itertext() directly, mirroring the same pattern
    _parse_sections() already uses per-section (`" ".join("".join(section.itertext()).split())`).
    Joining SectionNode.text values instead would require re-parsing sections here and would
    miss any text outside <section> elements (e.g. schedules, preambles) — direct itertext()
    on the whole tree is both simpler and strictly more complete.
    """
    return " ".join("".join(root.itertext()).split())
