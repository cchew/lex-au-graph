from pathlib import Path
import pytest
from lexaugraph.loader import parse_act, load_corpus

FIXTURES = Path(__file__).parent / "fixtures"

INDEX_ENTRY = {
    "name": "Privacy Act 1988",
    "year": 1988,
    "number": 119,
    "effective_date": "2026-06-04",
    "xml_path": "xml/privacy-act-1988.xml",
}


def test_parse_act_returns_act_node():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    assert data.act_node.frbr_uri == "/akn/au/act/1988/119"
    assert data.act_node.title == "Privacy Act 1988"
    assert data.act_node.year == 1988
    assert data.act_node.compilation_date == "2026-06-04"


def test_parse_act_extracts_sections():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    eids = [s.eid for s in data.sections]
    assert "part-I__sec-6" in eids
    assert "part-I__sec-13" in eids


def test_parse_act_section_has_heading_and_text():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    sec6 = next(s for s in data.sections if s.eid == "part-I__sec-6")
    assert sec6.heading == "Interpretation"
    assert "personal information" in sec6.text


def test_parse_act_extracts_defined_terms():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    terms = {t.term for t in data.defined_terms}
    assert "personal information" in terms
    assert "sensitive information" in terms


def test_parse_act_defined_term_links_to_section():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    pi = next(t for t in data.defined_terms if t.term == "personal information")
    assert pi.section_eid == "part-I__sec-6"
    assert "identified individual" in pi.definition_text


def test_parse_act_defined_term_display_case():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    pi = next(t for t in data.defined_terms if t.term == "personal information")
    assert pi.display_term == "personal information"


def test_parse_act_extracts_same_act_ref():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    same_act_refs = [r for r in data.ref_edges if not r.is_cross_act]
    assert any(r.target_href == "#part-I__sec-6" for r in same_act_refs)


def test_parse_act_extracts_cross_act_ref():
    data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    cross_act_refs = [r for r in data.ref_edges if r.is_cross_act]
    assert any("Freedom of Information Act 1982" in r.ref_text for r in cross_act_refs)
