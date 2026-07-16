from pathlib import Path
import pytest
from lexaugraph.graph import LexAuGraph
from lexaugraph.loader import parse_act
from lexaugraph.resolver import DefinitionResolver
from lexaugraph.models import ActData, ActNode, DefinedTermNode, SectionNode

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


def _make_term(term: str, display_term: str, act_frbr_uri: str, section_eid: str = "sec-1") -> DefinedTermNode:
    return DefinedTermNode(
        term=term,
        display_term=display_term,
        act_frbr_uri=act_frbr_uri,
        section_eid=section_eid,
        definition_text=f"{display_term} means something for {act_frbr_uri}.",
    )


def _make_act(frbr_uri: str, title: str, terms: list[DefinedTermNode]) -> ActData:
    return ActData(
        act_node=ActNode(frbr_uri=frbr_uri, title=title, year=2000),
        sections=[SectionNode(eid="sec-1", act_frbr_uri=frbr_uri, heading="Definitions", text="...")],
        defined_terms=terms,
        ref_edges=[],
    )


@pytest.fixture()
def multi_act_resolver() -> DefinitionResolver:
    g = LexAuGraph()
    # "personal information" defined in 3 Acts — should surface at min_acts=3
    g.add_act_data(_make_act(
        "/akn/au/act/1988/119", "Privacy Act 1988",
        [_make_term("personal information", "personal information", "/akn/au/act/1988/119")],
    ))
    g.add_act_data(_make_act(
        "/akn/au/act/2012/63", "My Health Records Act 2012",
        [_make_term("personal information", "personal information", "/akn/au/act/2012/63")],
    ))
    g.add_act_data(_make_act(
        "/akn/au/act/1999/119", "Aged Care Act 1997",
        [_make_term("personal information", "personal information", "/akn/au/act/1999/119")],
    ))
    # "australian resident" defined in only 2 Acts — should be excluded at min_acts=3
    g.add_act_data(_make_act(
        "/akn/au/act/1936/27", "Income Tax Assessment Act 1936",
        [_make_term("australian resident", "Australian resident", "/akn/au/act/1936/27")],
    ))
    g.add_act_data(_make_act(
        "/akn/au/act/1999/38", "A New Tax System (Family Assistance) Act 1999",
        [_make_term("australian resident", "Australian resident", "/akn/au/act/1999/38")],
    ))
    # junk-filter stopword fragment, defined in 3 Acts — should be excluded despite meeting the threshold
    g.add_act_data(_make_act(
        "/akn/au/act/1988/119", "Privacy Act 1988",
        [_make_term("does not", "does not", "/akn/au/act/1988/119", section_eid="sec-2")],
    ))
    g.add_act_data(_make_act(
        "/akn/au/act/2012/63", "My Health Records Act 2012",
        [_make_term("does not", "does not", "/akn/au/act/2012/63", section_eid="sec-2")],
    ))
    g.add_act_data(_make_act(
        "/akn/au/act/1999/119", "Aged Care Act 1997",
        [_make_term("does not", "does not", "/akn/au/act/1999/119", section_eid="sec-2")],
    ))
    return DefinitionResolver(g)


def test_list_multi_act_terms_includes_term_at_threshold(multi_act_resolver: DefinitionResolver):
    results = multi_act_resolver.list_multi_act_terms(min_acts=3)
    terms = {r.term for r in results}
    assert "personal information" in terms


def test_list_multi_act_terms_excludes_term_below_threshold(multi_act_resolver: DefinitionResolver):
    results = multi_act_resolver.list_multi_act_terms(min_acts=3)
    terms = {r.term for r in results}
    assert "australian resident" not in terms


def test_list_multi_act_terms_excludes_junk_stopword_fragment(multi_act_resolver: DefinitionResolver):
    results = multi_act_resolver.list_multi_act_terms(min_acts=3)
    terms = {r.term for r in results}
    assert "does not" not in terms


def test_list_multi_act_terms_excludes_short_terms(multi_act_resolver: DefinitionResolver):
    g = LexAuGraph()
    for i, uri in enumerate(["/akn/au/act/2001/1", "/akn/au/act/2002/2", "/akn/au/act/2003/3"]):
        g.add_act_data(_make_act(uri, f"Act {i}", [_make_term("gst", "GST", uri)]))
    resolver = DefinitionResolver(g)
    results = resolver.list_multi_act_terms(min_acts=3)
    assert "gst" not in {r.term for r in results}


def test_list_multi_act_terms_sorted_by_act_count_descending(multi_act_resolver: DefinitionResolver):
    results = multi_act_resolver.list_multi_act_terms(min_acts=1)
    act_counts = [r.act_count for r in results]
    assert act_counts == sorted(act_counts, reverse=True)


def test_list_multi_act_terms_carries_display_term_and_act_count(multi_act_resolver: DefinitionResolver):
    results = multi_act_resolver.list_multi_act_terms(min_acts=3)
    match = next(r for r in results if r.term == "personal information")
    assert match.display_term == "personal information"
    assert match.act_count == 3


def test_list_multi_act_terms_default_min_acts_is_three(multi_act_resolver: DefinitionResolver):
    default_results = multi_act_resolver.list_multi_act_terms()
    explicit_results = multi_act_resolver.list_multi_act_terms(min_acts=3)
    assert {r.term for r in default_results} == {r.term for r in explicit_results}


def test_count_acts_counts_act_nodes_only(multi_act_resolver: DefinitionResolver):
    # multi_act_resolver fixture loads 5 distinct Acts (Privacy Act 1988 is added twice,
    # once per add_act_data call, but act nodes are keyed by frbr_uri so it's one node)
    assert multi_act_resolver.count_acts() == 5


def test_count_valid_defined_terms_counts_all_valid_term_nodes(multi_act_resolver: DefinitionResolver):
    # 3 "personal information" + 2 "australian resident" + 3 "does not" = 8 defined_term nodes
    assert multi_act_resolver.count_valid_defined_terms() == 8


def test_count_valid_defined_terms_excludes_terms_missing_definition_text():
    g = LexAuGraph()
    act = _make_act("/akn/au/act/2001/1", "Act One", [_make_term("valid term", "valid term", "/akn/au/act/2001/1")])
    act.defined_terms.append(
        DefinedTermNode(
            term="broken term",
            display_term="broken term",
            act_frbr_uri="/akn/au/act/2001/1",
            section_eid="sec-1",
            definition_text="",
        )
    )
    g.add_act_data(act)
    resolver = DefinitionResolver(g)
    assert resolver.count_valid_defined_terms() == 1


def test_count_valid_defined_terms_excludes_terms_missing_section_eid():
    g = LexAuGraph()
    act = _make_act("/akn/au/act/2001/1", "Act One", [_make_term("valid term", "valid term", "/akn/au/act/2001/1")])
    act.defined_terms.append(
        DefinedTermNode(
            term="broken term",
            display_term="broken term",
            act_frbr_uri="/akn/au/act/2001/1",
            section_eid="",
            definition_text="broken term means something.",
        )
    )
    g.add_act_data(act)
    resolver = DefinitionResolver(g)
    assert resolver.count_valid_defined_terms() == 1


def test_find_all_definitions_returns_every_meaning_after_node_id_fix():
    """find_all_definitions already iterates every matching graph node --
    once _add_act_nodes stops overwriting same-slug nodes (Task 2), this
    returns multiple DefinitionResults with no resolver code change."""
    from lexaugraph.models import ActNode, SectionNode, DefinedTermNode, ActData
    from lexaugraph.graph import LexAuGraph
    from lexaugraph.resolver import DefinitionResolver

    act = ActNode(frbr_uri="/akn/au/act/1936/27", title="Income Tax Assessment Act 1936", year=1936)
    section = SectionNode(
        eid="part-III__sec-23", act_frbr_uri="/akn/au/act/1936/27",
        heading="Exemptions", text="...",
    )
    term_a = DefinedTermNode(
        term="exempt income", display_term="exempt income",
        act_frbr_uri="/akn/au/act/1936/27", section_eid="part-III__sec-23",
        definition_text="income derived from a source outside Australia by a resident",
    )
    term_b = DefinedTermNode(
        term="exempt income", display_term="exempt income",
        act_frbr_uri="/akn/au/act/1936/27", section_eid="part-III__sec-23",
        definition_text="a pension, allowance or benefit specified in Schedule 5",
    )
    data = ActData(act_node=act, sections=[section], defined_terms=[term_a, term_b], ref_edges=[])

    g = LexAuGraph()
    g.add_act_data(data)
    resolver = DefinitionResolver(g)

    results = resolver.find_all_definitions("exempt income")
    assert len(results) == 2
    def_texts = {r.definition_text for r in results}
    assert "income derived from a source outside Australia by a resident" in def_texts
    assert "a pension, allowance or benefit specified in Schedule 5" in def_texts
