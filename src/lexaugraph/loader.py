from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional

import lxml.etree as ET

from .models import ActData, ActNode, DefinedTermNode, RefEdge, SectionNode

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN = f"{{{AKN_NS}}}"


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
    index = json.loads((corpus_dir / "index.json").read_text())
    result = []
    for entry in index["acts"].values():
        xml_path = corpus_dir / entry["xml_path"]
        if xml_path.exists():
            result.append(parse_act(xml_path, entry))
        else:
            print(f"Warning: XML not found: {xml_path}", file=sys.stderr)
    return result


def _parse_act_node(root: ET._Element, index_entry: dict) -> ActNode:
    work_uri_el = root.find(f".//{AKN}FRBRWork/{AKN}FRBRuri")
    frbr_uri = work_uri_el.get("value", "").rstrip("/") if work_uri_el is not None else ""

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
                target_href=href,
                ref_text=ref_text,
                is_cross_act=is_cross_act,
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
        def_text = "".join(def_el.itertext()).strip().rstrip(".")
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
