from lexaugraph.models import (
    ActNode, SectionNode, DefinedTermNode, RefEdge, ActData, DefinitionResult,
    RelationType, _confidence_label,
)


def test_section_node_id():
    s = SectionNode(
        eid="part-I__sec-6",
        act_frbr_uri="/akn/au/act/1988/119",
        heading="Interpretation",
        text="In this Act...",
        provision_type="section",
    )
    assert s.node_id == "/akn/au/act/1988/119#part-I__sec-6"


def test_defined_term_node_id():
    t = DefinedTermNode(
        term="personal information",
        display_term="personal information",
        act_frbr_uri="/akn/au/act/1988/119",
        section_eid="part-I__sec-6",
        definition_text="information or an opinion about an identified individual",
    )
    assert t.node_id == "/akn/au/act/1988/119#term-personal_information"


def test_defined_term_node_id_default_occurrence_unchanged():
    """Default occurrence=1 must produce exactly today's node_id -- no
    suffix -- so every non-colliding term (the vast majority) is unaffected."""
    t = DefinedTermNode(
        term="personal information",
        display_term="personal information",
        act_frbr_uri="/akn/au/act/1988/119",
        section_eid="part-I__sec-6",
        definition_text="information or an opinion about an identified individual",
    )
    assert t.occurrence == 1
    assert t.node_id == "/akn/au/act/1988/119#term-personal_information"


def test_defined_term_node_id_second_occurrence_suffixed():
    """occurrence=2 appends a __2 suffix, keeping the two nodes distinct."""
    t = DefinedTermNode(
        term="exempt income",
        display_term="exempt income",
        act_frbr_uri="/akn/au/act/1936/27",
        section_eid="part-III__sec-23",
        definition_text="income derived from a source outside Australia by a person who is a resident",
        occurrence=2,
    )
    assert t.node_id == "/akn/au/act/1936/27#term-exempt_income__2"


def test_defined_term_node_id_third_occurrence_suffixed():
    t = DefinedTermNode(
        term="exempt income",
        display_term="exempt income",
        act_frbr_uri="/akn/au/act/1936/27",
        section_eid="part-III__sec-23",
        definition_text="a pension, allowance or benefit specified in Schedule 5",
        occurrence=3,
    )
    assert t.node_id == "/akn/au/act/1936/27#term-exempt_income__3"


def test_act_data_structure():
    act = ActNode(frbr_uri="/akn/au/act/1988/119", title="Privacy Act 1988", year=1988, compilation_date="2026-06-04")
    data = ActData(act_node=act, sections=[], defined_terms=[], ref_edges=[])
    assert data.act_node.title == "Privacy Act 1988"


def test_definition_result():
    r = DefinitionResult(
        term="personal information",
        display_term="personal information",
        definition_text="information or an opinion",
        act_frbr_uri="/akn/au/act/1988/119",
        section_eid="part-I__sec-6",
        act_title="Privacy Act 1988",
    )
    assert r.act_title == "Privacy Act 1988"


def test_ref_edge_defaults_target_href_and_matched_title_to_none():
    r = RefEdge(source_id="/akn/au/act/1988/119#sec-1", ref_text="the Corporations Act 2001", is_cross_act=True)
    assert r.target_href is None
    assert r.matched_title is None


def test_ref_edge_matched_title_set_for_untagged_path():
    r = RefEdge(
        source_id="/akn/au/act/1988/119#sec-1",
        ref_text="Corporations Act 2001",
        is_cross_act=True,
        target_href=None,
        matched_title="corporations act 2001",
    )
    assert r.matched_title == "corporations act 2001"


def test_ref_edge_defaults_matched_section_to_none():
    r = RefEdge(source_id="/akn/au/act/1988/119#sec-1", ref_text="section 6", is_cross_act=False)
    assert r.matched_section is None


def test_ref_edge_matched_section_set_for_intra_act_path():
    r = RefEdge(
        source_id="/akn/au/act/1988/119#sec-13",
        ref_text="section 6",
        is_cross_act=False,
        target_href=None,
        matched_title=None,
        matched_section="6",
    )
    assert r.matched_section == "6"


def test_impacted_node_fields():
    from lexaugraph.models import ImpactedNode
    n = ImpactedNode(
        node_id="/akn/au/act/1988/119#part-I__sec-13",
        hop=1,
        path_weight=3.0,
        ref_texts=["section 6"],
    )
    assert n.node_id == "/akn/au/act/1988/119#part-I__sec-13"
    assert n.hop == 1
    assert n.path_weight == 3.0
    assert n.ref_texts == ["section 6"]


def test_act_node_title_id_defaults_to_none():
    node = ActNode(frbr_uri="/akn/au/act/1988/119", title="Privacy Act 1988", year=1988)
    assert node.title_id is None


def test_act_node_legislation_url_none_when_no_title_id():
    node = ActNode(frbr_uri="/akn/au/act/1988/119", title="Privacy Act 1988", year=1988)
    assert node.legislation_url is None


def test_act_node_legislation_url_built_from_title_id():
    node = ActNode(
        frbr_uri="/akn/au/act/1988/119",
        title="Privacy Act 1988",
        year=1988,
        title_id="C2004A03712",
    )
    assert node.legislation_url == "https://www.legislation.gov.au/C2004A03712/latest/text"


def test_relation_type_values():
    assert RelationType.AMENDS == "amends"
    assert RelationType.REPEALS == "repeals"
    assert RelationType.CITES == "cites"
    assert RelationType.REFERENCES_DEFINITION == "references_definition"


def test_confidence_label_high_at_or_above_point_eight():
    assert _confidence_label(0.8) == "high"
    assert _confidence_label(1.0) == "high"


def test_confidence_label_medium_between_point_five_and_point_eight():
    assert _confidence_label(0.5) == "medium"
    assert _confidence_label(0.79) == "medium"


def test_confidence_label_low_below_point_five():
    assert _confidence_label(0.49) == "low"
    assert _confidence_label(0.0) == "low"


def test_ref_edge_defaults_relation_to_cites():
    r = RefEdge(source_id="/akn/au/act/1988/119#sec-1", ref_text="the Corporations Act 2001", is_cross_act=True)
    assert r.relation == RelationType.CITES


def test_ref_edge_relation_confidence_label_property():
    r = RefEdge(
        source_id="/akn/au/act/1988/119#sec-1", ref_text="x", is_cross_act=True,
        relation_confidence=0.9,
    )
    assert r.relation_confidence_label == "high"


def test_ref_edge_extraction_confidence_label_property():
    r = RefEdge(
        source_id="/akn/au/act/1988/119#sec-1", ref_text="x", is_cross_act=True,
        extraction_confidence=0.4,
    )
    assert r.extraction_confidence_label == "low"


def test_defined_term_node_entity_type_defaults_to_none():
    term = DefinedTermNode(
        term="personal information", display_term="personal information",
        act_frbr_uri="/akn/au/act/1988/119", section_eid="part-I__sec-6",
        definition_text="...",
    )
    assert term.entity_type is None


def test_defined_term_node_entity_type_can_be_set():
    term = DefinedTermNode(
        term="commissioner", display_term="Commissioner",
        act_frbr_uri="/akn/au/act/1988/119", section_eid="part-I__sec-6",
        definition_text="...", entity_type="commissioner",
    )
    assert term.entity_type == "commissioner"


def test_act_complexity_holds_all_four_metrics():
    from lexaugraph.models import ActComplexity
    c = ActComplexity(
        act_frbr_uri="/akn/au/act/1988/119",
        title="Privacy Act 1988",
        pagerank_centrality=0.0125,
        raw_citation_count=42,
        defined_term_count=10,
        defined_term_density=0.005,
        indeterminate_concept_count=3,
        indeterminate_concept_density=0.0015,
        conditional_statement_count=7,
        conditional_statement_density=0.0035,
        word_count=2000,
    )
    assert c.act_frbr_uri == "/akn/au/act/1988/119"
    assert c.word_count == 2000


def test_provision_codifiability_holds_all_signals_with_llm_signals_none():
    from lexaugraph.models import ProvisionCodifiability
    p = ProvisionCodifiability(
        eid="part-I__sec-6",
        act_frbr_uri="/akn/au/act/1988/119",
        llm_tag=None,
        llm_reasoning=None,
        vagueness_tag=None,
        vagueness_reasoning=None,
        prescriptive_density_count=3,
        prescriptive_density_regdata_subset_count=2,
        prescriptive_density_tag="medium",
        agreement="not_computed",
        parse_verification_status="not_yet_checked",
    )
    assert p.eid == "part-I__sec-6"
    assert p.llm_tag is None
    assert p.agreement == "not_computed"
