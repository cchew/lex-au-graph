from lexaugraph.models import (
    ActNode, SectionNode, DefinedTermNode, RefEdge, ActData, DefinitionResult
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
