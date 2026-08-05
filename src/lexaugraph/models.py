from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional


class RelationType(str, Enum):
    AMENDS = "amends"
    REPEALS = "repeals"
    CITES = "cites"
    REFERENCES_DEFINITION = "references_definition"


def _confidence_label(score: float) -> Literal["high", "medium", "low"]:
    # Thresholds are a first-pass calibration -- not independently validated.
    # See scripts/verify_relation_classification.py for real-corpus sampling.
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


@dataclass
class ActNode:
    frbr_uri: str
    title: str
    year: int
    compilation_date: Optional[str] = None
    title_id: Optional[str] = None

    @property
    def legislation_url(self) -> Optional[str]:
        if not self.title_id:
            return None
        return f"https://www.legislation.gov.au/{self.title_id}/latest/text"


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
    entity_type: Optional[str] = None

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
    matched_section: Optional[str] = None
    relation: RelationType = RelationType.CITES
    relation_confidence: float = 0.75
    extraction_confidence: float = 0.6

    @property
    def relation_confidence_label(self) -> Literal["high", "medium", "low"]:
        return _confidence_label(self.relation_confidence)

    @property
    def extraction_confidence_label(self) -> Literal["high", "medium", "low"]:
        return _confidence_label(self.extraction_confidence)


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


@dataclass
class ImpactedNode:
    node_id: str
    hop: int
    path_weight: float
    ref_texts: list[str]


@dataclass
class ActComplexity:
    act_frbr_uri: str
    title: str
    # 1. Cross-reference
    pagerank_centrality: float
    raw_citation_count: int
    # 2. Defined-term density
    defined_term_count: int
    defined_term_density: float
    # 3. Indeterminate-concept frequency (ALRC: reasonableness + good faith + unfair + fair + unjust)
    indeterminate_concept_count: int
    indeterminate_concept_density: float
    # 4. Conditional-statement frequency (ALRC's 9-word list)
    conditional_statement_count: int
    conditional_statement_density: float
    word_count: int


@dataclass
class ProvisionCodifiability:
    eid: str
    act_frbr_uri: str
    # Signal 1 -- LLM holistic judgment. None until --llm-signals has run.
    llm_tag: Optional[Literal["low", "medium", "high"]]
    llm_reasoning: Optional[str]
    # Signal 2 -- vagueness/open-texture. None until --llm-signals has run.
    vagueness_tag: Optional[Literal["low", "medium", "high"]]
    vagueness_reasoning: Optional[str]
    # Signal 3 -- prescriptive-language density. Always computed, free.
    prescriptive_density_count: int
    prescriptive_density_regdata_subset_count: int
    prescriptive_density_tag: Literal["low", "medium", "high"]
    # Corroboration
    agreement: Literal["full", "partial", "none", "not_computed"]
    # Parse-verification (Act-level fact, denormalized per provision)
    parse_verification_status: Literal["spot_checked", "not_yet_checked"]
