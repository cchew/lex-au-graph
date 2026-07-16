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
    occurrence: int = 1

    @property
    def node_id(self) -> str:
        slug = self.term.replace(" ", "_").replace("-", "_")
        base = f"{self.act_frbr_uri}#term-{slug}"
        if self.occurrence > 1:
            return f"{base}__{self.occurrence}"
        return base


@dataclass
class RefEdge:
    source_id: str
    ref_text: str
    is_cross_act: bool
    target_href: Optional[str] = None
    matched_title: Optional[str] = None


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


@dataclass
class MultiActTermSummary:
    term: str
    display_term: str
    act_count: int
