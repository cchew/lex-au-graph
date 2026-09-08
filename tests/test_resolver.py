from pathlib import Path
import pytest
from lexaugraph.graph import LexAuGraph
from lexaugraph.loader import parse_act
from lexaugraph.resolver import DefinitionResolver
from lexaugraph.models import ActData, ActNode, DefinedTermNode, SectionNode, RefEdge, RelationType

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


def test_passes_term_junk_filter():
    r = DefinitionResolver(LexAuGraph())
    assert r._passes_term_junk_filter("control") is True
    assert r._passes_term_junk_filter("xyz") is False        # len < 4
    assert r._passes_term_junk_filter("and") is False        # _JUNK_TERM_PATTERN
    assert r._passes_term_junk_filter("does not") is False


def test_term_act_counts_counts_distinct_acts(multi_act_resolver):
    counts = multi_act_resolver._term_act_counts()
    assert counts["personal information"] == 3
    assert counts["does not"] == 3


def test_term_act_counts_is_memoised(multi_act_resolver, monkeypatch):
    calls = {"n": 0}
    real_nodes_method = multi_act_resolver._graph.graph.nodes
    def counting_nodes(*a, **k):
        calls["n"] += 1
        return real_nodes_method(*a, **k)
    monkeypatch.setattr(multi_act_resolver._graph.graph, "nodes", counting_nodes)
    multi_act_resolver._term_act_counts()
    multi_act_resolver._term_act_counts()
    assert calls["n"] <= 1  # built once, then cached


def test_list_multi_act_terms_unchanged_after_refactor(multi_act_resolver):
    # Golden: capture the summaries at min_acts=3 threshold (personal information and control).
    summaries = multi_act_resolver.list_multi_act_terms(min_acts=3)
    assert sorted([s.term for s in summaries]) == ["control", "personal information"]


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


def test_cross_references_returns_one_entry_per_citation_on_shared_edge():
    act = ActNode(frbr_uri="/akn/au/act/1999/1", title="Sample Act 1999", year=1999)
    section_6 = SectionNode(eid="part-I__sec-6", act_frbr_uri=act.frbr_uri, heading="Definitions", text="...")
    section_13 = SectionNode(eid="part-I__sec-13", act_frbr_uri=act.frbr_uri, heading="Application", text="...")
    refs = [
        RefEdge(source_id=section_13.node_id, ref_text="section 6", is_cross_act=False,
                target_href=None, matched_title=None, matched_section="6",
                relation=RelationType.CITES, relation_confidence=0.75, extraction_confidence=0.6),
        RefEdge(source_id=section_13.node_id, ref_text="s 6", is_cross_act=False,
                target_href=None, matched_title=None, matched_section="6",
                relation=RelationType.REFERENCES_DEFINITION, relation_confidence=0.85, extraction_confidence=0.6),
    ]
    data = ActData(act_node=act, sections=[section_6, section_13], defined_terms=[], ref_edges=refs)
    g = LexAuGraph()
    g.add_act_data(data)
    resolver = DefinitionResolver(g)

    results = resolver.cross_references("part-I__sec-13", "/akn/au/act/1999/1")

    assert len(results) == 2
    relations = {r["relation"] for r in results}
    assert relations == {"cites", "references_definition"}
    assert all(r["is_cross_act"] is False for r in results)
    assert all("relation_confidence_label" in r and "extraction_confidence_label" in r for r in results)


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
        [
            _make_term("personal information", "personal information", "/akn/au/act/1988/119"),
            _make_term("control", "control", "/akn/au/act/1988/119", section_eid="sec-3"),
            _make_term("xydefined", "xydefined", "/akn/au/act/1988/119", section_eid="sec-4"),
        ],
    ))
    g.add_act_data(_make_act(
        "/akn/au/act/2012/63", "My Health Records Act 2012",
        [
            _make_term("personal information", "personal information", "/akn/au/act/2012/63"),
            _make_term("control", "control", "/akn/au/act/2012/63", section_eid="sec-3"),
        ],
    ))
    g.add_act_data(_make_act(
        "/akn/au/act/1999/119", "Aged Care Act 1997",
        [
            _make_term("personal information", "personal information", "/akn/au/act/1999/119"),
            _make_term("control", "control", "/akn/au/act/1999/119", section_eid="sec-3"),
        ],
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
    # 3 "personal information" + 2 "australian resident" + 3 "does not" + 3 "control" + 1 "xydefined" = 12 defined_term nodes
    assert multi_act_resolver.count_valid_defined_terms() == 12


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


@pytest.fixture()
def impact_resolver() -> DefinitionResolver:
    """Small synthetic Act: sec-6 (to be amended) is cited directly by
    sec-13 (hop 1) and indirectly by sec-20, which cites sec-13 (hop 2).
    sec-99 cites nothing and is cited by nothing -- the zero-citers case."""
    act = ActNode(frbr_uri="/akn/au/act/1999/1", title="Sample Act 1999", year=1999)
    sec_amend = SectionNode(eid="sec-6", act_frbr_uri=act.frbr_uri, heading="Amended", text="...")
    sec_direct = SectionNode(eid="sec-13", act_frbr_uri=act.frbr_uri, heading="Direct citer", text="...")
    sec_indirect = SectionNode(eid="sec-20", act_frbr_uri=act.frbr_uri, heading="Indirect citer", text="...")
    sec_untouched = SectionNode(eid="sec-99", act_frbr_uri=act.frbr_uri, heading="Untouched", text="...")
    refs = [
        RefEdge(source_id=sec_direct.node_id, ref_text="section 6", is_cross_act=False,
                target_href=None, matched_title=None, matched_section="6"),
        RefEdge(source_id=sec_indirect.node_id, ref_text="section 13", is_cross_act=False,
                target_href=None, matched_title=None, matched_section="13"),
    ]
    data = ActData(
        act_node=act,
        sections=[sec_amend, sec_direct, sec_indirect, sec_untouched],
        defined_terms=[],
        ref_edges=refs,
    )
    g = LexAuGraph()
    g.add_act_data(data)
    return DefinitionResolver(g)


def test_impacted_by_returns_empty_list_for_zero_citers(impact_resolver: DefinitionResolver):
    results = impact_resolver.impacted_by("sec-99", "/akn/au/act/1999/1")
    assert results == []


def test_impacted_by_direct_and_indirect_citers(impact_resolver: DefinitionResolver):
    results = impact_resolver.impacted_by("sec-6", "/akn/au/act/1999/1")
    by_id = {r["node_id"]: r for r in results}
    assert by_id["/akn/au/act/1999/1#sec-13"]["hop"] == 1
    assert by_id["/akn/au/act/1999/1#sec-20"]["hop"] == 2
    assert by_id["/akn/au/act/1999/1#sec-20"]["path_weight"] == pytest.approx(
        by_id["/akn/au/act/1999/1#sec-13"]["path_weight"] * 0.5
    )


def test_impacted_by_ref_texts_present(impact_resolver: DefinitionResolver):
    results = impact_resolver.impacted_by("sec-6", "/akn/au/act/1999/1")
    by_id = {r["node_id"]: r for r in results}
    assert by_id["/akn/au/act/1999/1#sec-13"]["ref_texts"] == ["section 6"]


def test_impacted_by_annotates_centrality_percentile_when_provided(impact_resolver: DefinitionResolver):
    scores = {
        "/akn/au/act/1999/1#sec-13": 0.1,
        "/akn/au/act/1999/1#sec-20": 0.9,
    }
    resolver_with_centrality = DefinitionResolver(impact_resolver._graph, centrality=scores)

    results = resolver_with_centrality.impacted_by("sec-6", "/akn/au/act/1999/1")

    by_id = {r["node_id"]: r for r in results}
    assert by_id["/akn/au/act/1999/1#sec-20"]["centrality_percentile"] == 100.0
    assert by_id["/akn/au/act/1999/1#sec-13"]["centrality_percentile"] == 0.0


def test_impacted_by_omits_percentile_key_when_no_centrality_provided(impact_resolver: DefinitionResolver):
    results = impact_resolver.impacted_by("sec-6", "/akn/au/act/1999/1")
    assert all("centrality_percentile" not in r for r in results)


def test_impacted_by_percentile_key_present_as_none_for_unscored_node(impact_resolver: DefinitionResolver):
    # Partial centrality dict: scores sec-13 but deliberately omits sec-20, which
    # impacted_by("sec-6", ...) also returns. sec-20's result dict must still carry
    # the "centrality_percentile" key -- with value None -- not silently drop it.
    scores = {
        "/akn/au/act/1999/1#sec-13": 0.1,
    }
    resolver_with_centrality = DefinitionResolver(impact_resolver._graph, centrality=scores)

    results = resolver_with_centrality.impacted_by("sec-6", "/akn/au/act/1999/1")

    by_id = {r["node_id"]: r for r in results}
    assert "centrality_percentile" in by_id["/akn/au/act/1999/1#sec-20"]
    assert by_id["/akn/au/act/1999/1#sec-20"]["centrality_percentile"] is None


COLLISION_INDEX_ENTRY = {
    "name": "Levy and Charges Act 2026",
    "year": 2026,
    "number": 1,
    "effective_date": "2026-01-01",
    "xml_path": "xml/collision-test-act.xml",
}


@pytest.fixture()
def collision_resolver() -> DefinitionResolver:
    act_data = parse_act(FIXTURES / "collision-test-act.xml", COLLISION_INDEX_ENTRY)
    g = LexAuGraph()
    g.add_act_data(act_data)
    return DefinitionResolver(g)


def test_resolve_definition_exact_section_match(collision_resolver: DefinitionResolver):
    result = collision_resolver.resolve_definition(
        "levy", "/akn/au/act/2026/1", section_eid="part-I__dvs-1__sec-5"
    )
    assert result is not None
    assert result.section_eid == "part-I__dvs-1__sec-5"
    assert "Division 1" in result.definition_text


def test_resolve_definition_nearest_enclosing_division(collision_resolver: DefinitionResolver):
    # sec-6 doesn't define "levy" itself, but it's in the same Division (dvs-1)
    # as sec-5's definition. Three competing "levy" definitions exist: Part II
    # (different Part -- out of scope), Part I/Division 2 (same Part, but a
    # *different* Division -- would win under Part-only scoping, so this pins
    # true Division-level granularity), and Part I/Division 1 sec-5 (same
    # Division as the query -- the only correct answer). Only a resolver that
    # actually scopes to Division, not just Part, picks sec-5 here.
    result = collision_resolver.resolve_definition(
        "levy", "/akn/au/act/2026/1", section_eid="part-I__dvs-1__sec-6"
    )
    assert result is not None
    assert result.section_eid == "part-I__dvs-1__sec-5"


def test_resolve_definition_ambiguous_returns_none(collision_resolver: DefinitionResolver):
    # "charge" is defined in Part III and Part IV, neither of which
    # encloses Part V -- genuinely ambiguous, must not guess.
    result = collision_resolver.resolve_definition(
        "charge", "/akn/au/act/2026/1", section_eid="part-V__sec-300"
    )
    assert result is None


def test_resolve_definition_no_section_eid_keeps_old_behaviour(collision_resolver: DefinitionResolver):
    # Backward compatibility: omitting section_eid must still return *a*
    # match, not None, for every existing caller (cli.py, mcp.py).
    result = collision_resolver.resolve_definition("levy", "/akn/au/act/2026/1")
    assert result is not None


@pytest.fixture()
def registrar_resolver() -> DefinitionResolver:
    index_entry = {
        "name": "Sample Registrar Act 1961", "year": 1961, "number": 12,
        "effective_date": "2026-06-04", "xml_path": "xml/registrar-entity-sample.xml",
    }
    act_data = parse_act(FIXTURES / "registrar-entity-sample.xml", index_entry)
    g = LexAuGraph()
    g.add_act_data(act_data)
    return DefinitionResolver(g)


def test_entities_in_section_finds_mentioned_entity(registrar_resolver: DefinitionResolver):
    results = registrar_resolver.entities_in_section("part-II__sec-10", "/akn/au/act/1961/12")
    assert len(results) == 1
    assert results[0]["display_term"] == "Registrar"
    assert results[0]["entity_type"] == "registrar"
    assert results[0]["count"] == 2


def test_entities_in_section_empty_for_section_with_no_mentions(registrar_resolver: DefinitionResolver):
    # part-I__sec-5 defines both "Registrar" and "purpose"; "purpose" is
    # non-entity so only Registrar's defining-section self-mention shows up.
    results = registrar_resolver.entities_in_section("part-I__sec-5", "/akn/au/act/1961/12")
    assert [r["display_term"] for r in results] == ["Registrar"]


def test_find_entity_returns_act_scoped_result(registrar_resolver: DefinitionResolver):
    results = registrar_resolver.find_entity("Registrar")
    assert len(results) == 1
    assert results[0]["entity_type"] == "registrar"
    assert results[0]["act_title"] == "Sample Registrar Act 1961"
    assert results[0]["section_eid"] == "part-I__sec-5"


def test_find_entity_excludes_non_entity_terms(registrar_resolver: DefinitionResolver):
    assert registrar_resolver.find_entity("purpose") == []


def test_find_entity_no_match_returns_empty_list(registrar_resolver: DefinitionResolver):
    assert registrar_resolver.find_entity("nonexistent xyz") == []


@pytest.fixture()
def cross_act_resolver() -> DefinitionResolver:
    """Two-Act graph: Act A ('Alpha Act 2000') defines 'widget' as a pointer
    into Act B ('Beta Act 2001'), which defines 'widget' substantively in
    sec-3. Gamma Act 1999 is never loaded -- the out-of-corpus target case."""
    g = LexAuGraph()
    act_a = ActData(
        act_node=ActNode(frbr_uri="/akn/au/act/2000/1", title="Alpha Act 2000", year=2000),
        sections=[SectionNode(eid="sec-2", act_frbr_uri="/akn/au/act/2000/1", heading="Definitions", text="...")],
        defined_terms=[DefinedTermNode(
            term="widget", display_term="widget",
            act_frbr_uri="/akn/au/act/2000/1", section_eid="sec-2",
            definition_text="has the same meaning as in the Beta Act 2001",
        )],
        ref_edges=[],
    )
    act_b = ActData(
        act_node=ActNode(frbr_uri="/akn/au/act/2001/2", title="Beta Act 2001", year=2001),
        sections=[SectionNode(eid="sec-3", act_frbr_uri="/akn/au/act/2001/2", heading="Definitions", text="...")],
        defined_terms=[DefinedTermNode(
            term="widget", display_term="widget",
            act_frbr_uri="/akn/au/act/2001/2", section_eid="sec-3",
            definition_text="means a small mechanical part",
        )],
        ref_edges=[],
    )
    g.add_act_data(act_a)
    g.add_act_data(act_b)
    return DefinitionResolver(g)


def test_follow_cross_act_resolves_in_corpus(cross_act_resolver):
    out = cross_act_resolver._follow_cross_act(
        "widget", "has the same meaning as in the Beta Act 2001", "/akn/au/act/2000/1"
    )
    assert out["definition_text"] == "means a small mechanical part"
    assert out["via"] == {"act_title": "Beta Act 2001", "section_eid": "sec-3", "resolved": True}


def test_follow_cross_act_unresolved_when_act_absent(cross_act_resolver):
    out = cross_act_resolver._follow_cross_act(
        "widget", "has the same meaning as in the Gamma Act 1999", "/akn/au/act/2000/1"
    )
    assert out["definition_text"] == "has the same meaning as in the Gamma Act 1999"
    assert out["via"] == {"act_title": "Gamma Act 1999", "section_eid": None, "resolved": False}


def test_follow_cross_act_returns_none_for_substantive_def(cross_act_resolver):
    assert cross_act_resolver._follow_cross_act(
        "widget", "means a small mechanical part", "/akn/au/act/2001/2"
    ) is None


def test_follow_cross_act_no_self_loop(cross_act_resolver):
    # Pointer that names its own Act -> do not follow, treat as unresolved.
    out = cross_act_resolver._follow_cross_act(
        "widget", "has the same meaning as in the Alpha Act 2000", "/akn/au/act/2000/1"
    )
    assert out["via"]["resolved"] is False


MULTI_DEF_URI = "/akn/au/act/2020/50"
THREE_ACT_TERM_URI = "/akn/au/act/1988/119"


@pytest.fixture()
def multi_def_resolver() -> DefinitionResolver:
    """One Act that defines 'associate' in two sections: part-2__sec-10 and part-5__sec-40."""
    g = LexAuGraph()
    terms = [
        DefinedTermNode(
            term="associate", display_term="associate",
            act_frbr_uri=MULTI_DEF_URI, section_eid="part-2__sec-10",
            definition_text="means a person in partnership or joint venture",
        ),
        DefinedTermNode(
            term="associate", display_term="associate",
            act_frbr_uri=MULTI_DEF_URI, section_eid="part-5__sec-40",
            definition_text="means a person affiliated with the corporation",
        ),
    ]
    g.add_act_data(_make_act(MULTI_DEF_URI, "Corporations Act 2020", terms))
    return DefinitionResolver(g)


def test_get_act_definitions_groups_all_terms(cross_act_resolver):
    rows = cross_act_resolver.get_act_definitions("/akn/au/act/2001/2")
    assert {r["term"] for r in rows} == {"widget"}
    assert rows[0]["definition_text"] == "means a small mechanical part"
    assert rows[0]["section_eid"] == "sec-3"


def test_get_act_definitions_multiply_defined_yields_multiple_rows(multi_def_resolver):
    # Act defines "associate" in part-2__sec-10 and part-5__sec-40
    rows = [r for r in multi_def_resolver.get_act_definitions(MULTI_DEF_URI) if r["term"] == "associate"]
    assert sorted(r["section_eid"] for r in rows) == ["part-2__sec-10", "part-5__sec-40"]


def test_get_act_definitions_inlines_cross_act(cross_act_resolver):
    rows = cross_act_resolver.get_act_definitions("/akn/au/act/2000/1")
    row = next(r for r in rows if r["term"] == "widget")
    assert row["definition_text"] == "means a small mechanical part"
    assert row["via"]["resolved"] is True


def test_get_act_definitions_sets_act_alike(multi_act_resolver):
    rows = multi_act_resolver.get_act_definitions(THREE_ACT_TERM_URI)
    assert next(r for r in rows if r["term"] == "control")["act_alike"] is True
    assert next(r for r in rows if r["term"] == "xydefined")["act_alike"] is False  # 1 Act
