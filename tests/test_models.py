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
