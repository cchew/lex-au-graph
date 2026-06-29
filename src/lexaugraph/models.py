from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class ActNode:
    frbr_uri: str
    title: str
    year: int
    compilation_date: Optional[str] = None


@dataclass
class SectionNode:
    eid: str
    act_frbr_uri: str
    heading: Optional[str]
    text: str
    provision_type: str = "section"

    @property
    def node_id(self) -> str:
        return f"{self.act_frbr_uri}#{self.eid}"


@dataclass
class DefinedTermNode:
    term: str
    display_term: str
    act_frbr_uri: str
    section_eid: str
    definition_text: str

    @property
    def node_id(self) -> str:
        slug = self.term.replace(" ", "_").replace("-", "_")
        return f"{self.act_frbr_uri}#term-{slug}"


@dataclass
class RefEdge:
    source_id: str
    target_href: str
    ref_text: str
    is_cross_act: bool


@dataclass
class ActData:
    act_node: ActNode
    sections: list[SectionNode]
    defined_terms: list[DefinedTermNode]
    ref_edges: list[RefEdge]


@dataclass
class DefinitionResult:
    term: str
    display_term: str
    definition_text: str
    act_frbr_uri: str
    section_eid: str
    act_title: str
