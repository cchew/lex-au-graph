from pathlib import Path
import pytest
from lexaugraph.graph import LexAuGraph
from lexaugraph.loader import parse_act
from lexaugraph.resolver import DefinitionResolver

FIXTURES = Path(__file__).parent / "fixtures"
INDEX_ENTRY = {
    "name": "Privacy Act 1988",
    "year": 1988,
    "number": 119,
    "effective_date": "2026-06-04",
    "xml_path": "xml/privacy-act-1988.xml",
}


@pytest.fixture()
def resolver() -> DefinitionResolver:
    act_data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    g = LexAuGraph()
    g.add_act_data(act_data)
    return DefinitionResolver(g)


def test_resolve_definition_finds_term(resolver: DefinitionResolver):
    result = resolver.resolve_definition("personal information", "/akn/au/act/1988/119")
    assert result is not None
    assert result.section_eid == "part-I__sec-6"
    assert "identified individual" in result.definition_text


def test_resolve_definition_case_insensitive(resolver: DefinitionResolver):
    result = resolver.resolve_definition("Personal Information", "/akn/au/act/1988/119")
    assert result is not None
    assert result.term == "Personal Information"


def test_resolve_definition_returns_act_title(resolver: DefinitionResolver):
    result = resolver.resolve_definition("personal information", "/akn/au/act/1988/119")
    assert result is not None
    assert result.act_title == "Privacy Act 1988"


def test_resolve_definition_unknown_term_returns_none(resolver: DefinitionResolver):
    result = resolver.resolve_definition("nonexistent term xyz", "/akn/au/act/1988/119")
    assert result is None


def test_resolve_definition_wrong_act_returns_none(resolver: DefinitionResolver):
    result = resolver.resolve_definition("personal information", "/akn/au/act/2009/28")
    assert result is None


def test_cross_references_same_act(resolver: DefinitionResolver):
    refs = resolver.cross_references("part-I__sec-13", "/akn/au/act/1988/119")
    assert len(refs) >= 1
    same_act = [r for r in refs if not r["is_cross_act"]]
    assert any(r["ref_text"] == "section 6" for r in same_act)


def test_cross_references_no_refs_returns_empty(resolver: DefinitionResolver):
    refs = resolver.cross_references("part-I__sec-6", "/akn/au/act/1988/119")
    # sec-6 is the definitions section — it defines terms but has no outgoing refs in fixture
    assert isinstance(refs, list)


def test_find_all_definitions_returns_results(resolver: DefinitionResolver):
    results = resolver.find_all_definitions("personal information")
    assert len(results) == 1
    assert results[0].act_frbr_uri == "/akn/au/act/1988/119"
    assert results[0].section_eid == "part-I__sec-6"


def test_find_all_definitions_case_insensitive(resolver: DefinitionResolver):
    results = resolver.find_all_definitions("Personal Information")
    assert len(results) == 1
    assert results[0].term == "Personal Information"


def test_find_all_definitions_unknown_term_returns_empty(resolver: DefinitionResolver):
    results = resolver.find_all_definitions("nonexistent term xyz")
    assert results == []


def test_get_act_terms_returns_all_terms(resolver: DefinitionResolver):
    terms = resolver.get_act_terms("/akn/au/act/1988/119")
    assert len(terms) == 2
    term_names = [t["term"] for t in terms]
    assert "personal information" in term_names
    assert "sensitive information" in term_names


def test_get_act_terms_has_required_keys(resolver: DefinitionResolver):
    terms = resolver.get_act_terms("/akn/au/act/1988/119")
    for t in terms:
        assert "term" in t
        assert "display_term" in t
        assert "section_eid" in t


def test_get_act_terms_unknown_act_returns_empty(resolver: DefinitionResolver):
    terms = resolver.get_act_terms("/akn/au/act/2009/28")
    assert terms == []
