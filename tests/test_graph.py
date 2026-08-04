from pathlib import Path
import pytest
from lexaugraph.graph import LexAuGraph, _build_entity_mention_pattern
from lexaugraph.loader import parse_act
from lexaugraph.models import ActData, ActNode, DefinedTermNode, RefEdge, SectionNode, RelationType

FIXTURES = Path(__file__).parent / "fixtures"
INDEX_ENTRY = {
    "name": "Privacy Act 1988",
    "year": 1988,
    "number": 119,
    "effective_date": "2026-06-04",
    "xml_path": "xml/privacy-act-1988.xml",
    "title_id": "C2004A03712",
}


@pytest.fixture()
def act_data() -> ActData:
    return parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)


@pytest.fixture()
def graph_with_privacy(act_data: ActData) -> LexAuGraph:
    g = LexAuGraph()
    g.add_act_data(act_data)
    return g


def test_add_act_node(graph_with_privacy: LexAuGraph):
    assert "/akn/au/act/1988/119" in graph_with_privacy.graph.nodes
    node = graph_with_privacy.graph.nodes["/akn/au/act/1988/119"]
    assert node["type"] == "act"
    assert node["title"] == "Privacy Act 1988"


def test_add_act_node_carries_title_id(graph_with_privacy: LexAuGraph):
    node = graph_with_privacy.graph.nodes["/akn/au/act/1988/119"]
    assert node["title_id"] == "C2004A03712"


def test_add_section_nodes(graph_with_privacy: LexAuGraph):
    node_id = "/akn/au/act/1988/119#part-I__sec-6"
    assert node_id in graph_with_privacy.graph.nodes
    node = graph_with_privacy.graph.nodes[node_id]
    assert node["type"] == "section"
    assert node["heading"] == "Interpretation"


def test_contains_edges(graph_with_privacy: LexAuGraph):
    act_id = "/akn/au/act/1988/119"
    sec_id = "/akn/au/act/1988/119#part-I__sec-6"
    assert graph_with_privacy.graph.has_edge(act_id, sec_id)
    edge = graph_with_privacy.graph.edges[act_id, sec_id, "contains"]
    assert edge["type"] == "contains"


def test_defined_term_nodes(graph_with_privacy: LexAuGraph):
    term_id = "/akn/au/act/1988/119#term-personal_information"
    assert term_id in graph_with_privacy.graph.nodes
    node = graph_with_privacy.graph.nodes[term_id]
    assert node["type"] == "defined_term"
    assert node["term"] == "personal information"


def test_defines_edges(graph_with_privacy: LexAuGraph):
    sec_id = "/akn/au/act/1988/119#part-I__sec-6"
    term_id = "/akn/au/act/1988/119#term-personal_information"
    assert graph_with_privacy.graph.has_edge(sec_id, term_id)
    edge = graph_with_privacy.graph.edges[sec_id, term_id, "defines"]
    assert edge["type"] == "defines"


def test_multi_meaning_terms_survive_as_distinct_nodes():
    """Same-Act, same-slug terms with genuinely different definition_text
    (real OPC drafting -- e.g. ITAA 1936's 'exempt income' has 4 distinct
    meanings) must NOT silently overwrite each other in the graph. Confirmed
    bug before this fix: add_node's second call with the same node_id
    overwrites the first's attributes, and the first node is gone."""
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

    term_nodes = [
        n for n, d in g.graph.nodes(data=True)
        if d.get("type") == "defined_term" and d.get("term") == "exempt income"
    ]
    assert len(term_nodes) == 2

    def_texts = {g.graph.nodes[n]["definition_text"] for n in term_nodes}
    assert "income derived from a source outside Australia by a resident" in def_texts
    assert "a pension, allowance or benefit specified in Schedule 5" in def_texts

    # occurrence side effect is visible on the caller's objects
    assert term_a.occurrence == 1
    assert term_b.occurrence == 2


def test_same_act_ref_edge(graph_with_privacy: LexAuGraph):
    src = "/akn/au/act/1988/119#part-I__sec-13"
    tgt = "/akn/au/act/1988/119#part-I__sec-6"
    assert graph_with_privacy.graph.has_edge(src, tgt)
    edge = graph_with_privacy.graph.edges[src, tgt, "ref"]
    assert edge["type"] == "ref"


def test_defines_and_tagged_same_act_ref_to_same_term_coexist_without_crash():
    """Real-corpus bug (74 instances): a section that *defines* a term also
    carries an inline tagged <ref href="#term-X"> back to that same term, so the
    ref resolves to the exact same (section_id, term_node_id) pair the defines
    edge already occupies. On a plain DiGraph the second edge silently clobbered
    the first (data corruption); after Task 5's weight-tracking fix it crashed
    with KeyError: 'weight'. With a MultiDiGraph keyed per relationship type,
    both edges must coexist as distinct parallel edges."""
    act = ActNode(frbr_uri="/akn/au/act/2010/7", title="Collision Act 2010", year=2010)
    section = SectionNode(
        eid="part-I__sec-6", act_frbr_uri=act.frbr_uri, heading="Definitions", text="...",
    )
    term = DefinedTermNode(
        term="vclp", display_term="VCLP",
        act_frbr_uri=act.frbr_uri, section_eid="part-I__sec-6",
        definition_text="a venture capital limited partnership",
    )
    # Tagged same-Act ref from the defining section back to the term it defines.
    # target_href="#term-vclp" resolves to f"{act_frbr_uri}#term-vclp" == term.node_id.
    ref = RefEdge(
        source_id=section.node_id, ref_text="VCLP", is_cross_act=False,
        target_href="#term-vclp", matched_title=None, matched_section=None,
    )
    data = ActData(act_node=act, sections=[section], defined_terms=[term], ref_edges=[ref])

    g = LexAuGraph()
    g.add_act_data(data)  # must not raise

    src = section.node_id
    tgt = term.node_id
    # (a) both edges survive as distinct parallel edges keyed by type
    assert g.graph.has_edge(src, tgt, key="defines")
    assert g.graph.has_edge(src, tgt, key="ref")
    # (b)/(c) each carries its own correct type attribute
    assert g.graph.edges[src, tgt, "defines"]["type"] == "defines"
    ref_edge = g.graph.edges[src, tgt, "ref"]
    assert ref_edge["type"] == "ref"
    # (d) the ref edge got weight=1 and the expected ref_texts
    assert ref_edge["weight"] == 1
    assert ref_edge["ref_texts"] == ["VCLP"]


def test_single_ref_between_pair_gets_weight_one():
    act = ActNode(frbr_uri="/akn/au/act/1999/1", title="Sample Act 1999", year=1999)
    section_6 = SectionNode(eid="part-I__sec-6", act_frbr_uri=act.frbr_uri, heading="Definitions", text="...")
    section_13 = SectionNode(eid="part-I__sec-13", act_frbr_uri=act.frbr_uri, heading="Application", text="...")
    ref = RefEdge(
        source_id=section_13.node_id, ref_text="section 6", is_cross_act=False,
        target_href=None, matched_title=None, matched_section="6",
    )
    data = ActData(act_node=act, sections=[section_6, section_13], defined_terms=[], ref_edges=[ref])

    g = LexAuGraph()
    g.add_act_data(data)

    edge = g.graph.edges[section_13.node_id, section_6.node_id, "ref"]
    assert edge["weight"] == 1
    assert edge["ref_texts"] == ["section 6"]


def test_repeated_refs_between_same_pair_increment_weight_not_overwrite():
    act = ActNode(frbr_uri="/akn/au/act/1999/1", title="Sample Act 1999", year=1999)
    section_6 = SectionNode(eid="part-I__sec-6", act_frbr_uri=act.frbr_uri, heading="Definitions", text="...")
    section_13 = SectionNode(eid="part-I__sec-13", act_frbr_uri=act.frbr_uri, heading="Application", text="...")
    refs = [
        RefEdge(source_id=section_13.node_id, ref_text="section 6", is_cross_act=False,
                target_href=None, matched_title=None, matched_section="6"),
        RefEdge(source_id=section_13.node_id, ref_text="s 6", is_cross_act=False,
                target_href=None, matched_title=None, matched_section="6"),
        RefEdge(source_id=section_13.node_id, ref_text="subsection 6(2)", is_cross_act=False,
                target_href=None, matched_title=None, matched_section="6"),
    ]
    data = ActData(act_node=act, sections=[section_6, section_13], defined_terms=[], ref_edges=refs)

    g = LexAuGraph()
    g.add_act_data(data)

    edge = g.graph.edges[section_13.node_id, section_6.node_id, "ref"]
    assert edge["weight"] == 3
    assert edge["ref_texts"] == ["section 6", "s 6", "subsection 6(2)"]


def test_ref_edge_carries_citations_list_with_relation_and_confidence():
    act = ActNode(frbr_uri="/akn/au/act/1999/1", title="Sample Act 1999", year=1999)
    section_6 = SectionNode(eid="part-I__sec-6", act_frbr_uri=act.frbr_uri, heading="Definitions", text="...")
    section_13 = SectionNode(eid="part-I__sec-13", act_frbr_uri=act.frbr_uri, heading="Application", text="...")
    ref = RefEdge(
        source_id=section_13.node_id, ref_text="section 6", is_cross_act=False,
        target_href=None, matched_title=None, matched_section="6",
        relation=RelationType.REPEALS, relation_confidence=0.85, extraction_confidence=0.6,
    )
    data = ActData(act_node=act, sections=[section_6, section_13], defined_terms=[], ref_edges=[ref])

    g = LexAuGraph()
    g.add_act_data(data)

    edge = g.graph.edges[section_13.node_id, section_6.node_id, "ref"]
    assert edge["citations"] == [{
        "ref_text": "section 6",
        "relation": "repeals",
        "relation_confidence": 0.85,
        "extraction_confidence": 0.6,
    }]
    assert "ref_text" not in edge  # stale singular scalar is gone


def test_ref_edge_preserves_differing_relations_on_repeated_citations():
    # Two citations between the same section pair with DIFFERENT relations must
    # both survive -- the bug the independent spec review caught: a scalar
    # relation field would silently overwrite the first citation's classification.
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

    edge = g.graph.edges[section_13.node_id, section_6.node_id, "ref"]
    relations = [c["relation"] for c in edge["citations"]]
    assert relations == ["cites", "references_definition"]


def test_citations_list_is_json_serializable(tmp_path: Path):
    # Regression test for the spec-review finding: a CitationRecord dataclass
    # instance on a graph edge would silently corrupt via json.dumps(default=str)
    # on save, and load() could not reconstruct it. citations must be list[dict].
    act = ActNode(frbr_uri="/akn/au/act/1999/1", title="Sample Act 1999", year=1999)
    section_6 = SectionNode(eid="part-I__sec-6", act_frbr_uri=act.frbr_uri, heading="Definitions", text="...")
    section_13 = SectionNode(eid="part-I__sec-13", act_frbr_uri=act.frbr_uri, heading="Application", text="...")
    ref = RefEdge(
        source_id=section_13.node_id, ref_text="section 6", is_cross_act=False,
        target_href=None, matched_title=None, matched_section="6",
        relation=RelationType.AMENDS, relation_confidence=0.85, extraction_confidence=0.6,
    )
    data = ActData(act_node=act, sections=[section_6, section_13], defined_terms=[], ref_edges=[ref])
    g = LexAuGraph()
    g.add_act_data(data)

    path = tmp_path / "graph.json"
    g.save(path)
    loaded = LexAuGraph.load(path)

    edge = loaded.graph.edges[section_13.node_id, section_6.node_id, "ref"]
    assert edge["citations"] == [{
        "ref_text": "section 6",
        "relation": "amends",
        "relation_confidence": 0.85,
        "extraction_confidence": 0.6,
    }]


def test_repeated_pending_refs_to_same_target_increment_weight_on_retry(graph_with_privacy: LexAuGraph):
    # privacy-act-1988.xml's part-I__sec-13 has both a tagged and an untagged
    # citation to Freedom of Information Act 1982 (see test_citation_stats_bucket_totals
    # above: "1 tagged cross-act citation + 1 untagged, both to FOI"). Both queue into
    # _pending_refs before FOI is loaded (graph_with_privacy only has Privacy Act loaded);
    # adding FOI here triggers _retry_pending_refs for both. They must accumulate into
    # ONE weighted edge via _add_or_increment_ref_edge, not the second silently
    # overwriting the first's ref_text the way a bare add_edge call would.
    foi_data = parse_act(FIXTURES / "freedom-of-information-act-1982.xml", FOI_INDEX_ENTRY)
    graph_with_privacy.add_act_data(foi_data)

    src = "/akn/au/act/1988/119#part-I__sec-13"
    tgt = "/akn/au/act/1982/3"
    edge = graph_with_privacy.graph.edges[src, tgt, "ref"]
    assert edge["weight"] == 2
    assert len(edge["ref_texts"]) == 2


def test_stats_returns_counts(graph_with_privacy: LexAuGraph):
    stats = graph_with_privacy.stats()
    assert stats["nodes"] > 0
    assert "act" in stats["node_types"]
    assert "section" in stats["node_types"]
    assert "defined_term" in stats["node_types"]
    assert "contains" in stats["edge_types"]
    assert "defines" in stats["edge_types"]


def test_save_load_roundtrip(graph_with_privacy: LexAuGraph, tmp_path: Path):
    path = tmp_path / "graph.json"
    graph_with_privacy.save(path)
    assert path.exists()
    loaded = LexAuGraph.load(path)
    # MultiDiGraph class is self-described via the "multigraph": true JSON field
    # and reconstructed by node_link_graph -- no create_using needed.
    import networkx as nx
    assert isinstance(loaded.graph, nx.MultiDiGraph)
    assert loaded.graph.number_of_nodes() == graph_with_privacy.graph.number_of_nodes()
    assert loaded.graph.number_of_edges() == graph_with_privacy.graph.number_of_edges()
    # Act node survives roundtrip
    assert "/akn/au/act/1988/119" in loaded.graph.nodes
    # Keyed edges survive with their per-type attributes intact
    src = "/akn/au/act/1988/119#part-I__sec-13"
    tgt = "/akn/au/act/1988/119#part-I__sec-6"
    assert loaded.graph.has_edge(src, tgt, key="ref")
    ref_edge = loaded.graph.edges[src, tgt, "ref"]
    assert ref_edge["type"] == "ref"
    assert ref_edge["weight"] == graph_with_privacy.graph.edges[src, tgt, "ref"]["weight"]
    assert ref_edge["ref_texts"] == graph_with_privacy.graph.edges[src, tgt, "ref"]["ref_texts"]
    # title_id survives the JSON round-trip on the act node
    assert loaded.graph.nodes["/akn/au/act/1988/119"]["title_id"] == "C2004A03712"


def test_load_rejects_old_format_digraph(tmp_path: Path):
    import json
    import networkx as nx

    old_graph = nx.DiGraph()
    old_graph.add_node("/akn/au/act/1988/119", type="act", title="Privacy Act 1988")
    old_graph.add_node(
        "/akn/au/act/1988/119#part-I__sec-6", type="section", eid="part-I__sec-6"
    )
    old_graph.add_edge(
        "/akn/au/act/1988/119", "/akn/au/act/1988/119#part-I__sec-6", type="contains"
    )
    old_format_data = nx.node_link_data(old_graph, edges="edges")
    assert old_format_data["multigraph"] is False

    path = tmp_path / "graph.json"
    path.write_text(json.dumps(old_format_data, default=str))

    with pytest.raises(ValueError, match="(?i)rebuild"):
        LexAuGraph.load(path)


def test_get_sections(graph_with_privacy: LexAuGraph):
    sections = graph_with_privacy.get_sections("/akn/au/act/1988/119")
    eids = [s["eid"] for s in sections]
    assert "part-I__sec-6" in eids


def test_add_defined_term_adds_queryable_node_without_touching_act_or_section(
    graph_with_privacy: LexAuGraph,
):
    act_id = "/akn/au/act/1988/119"
    sec_id = "/akn/au/act/1988/119#part-I__sec-6"
    nodes_before = graph_with_privacy.graph.number_of_nodes()
    edges_before = graph_with_privacy.graph.number_of_edges()
    act_node_before = dict(graph_with_privacy.graph.nodes[act_id])
    sec_node_before = dict(graph_with_privacy.graph.nodes[sec_id])

    backfilled = DefinedTermNode(
        term="income support payment",
        display_term="income support payment",
        act_frbr_uri=act_id,
        section_eid="part-I__sec-6",
        definition_text="income support payment means a payment of a designated kind.",
    )
    graph_with_privacy.add_defined_term(backfilled)

    term_id = "/akn/au/act/1988/119#term-income_support_payment"
    assert term_id in graph_with_privacy.graph.nodes
    node = graph_with_privacy.graph.nodes[term_id]
    assert node["type"] == "defined_term"
    assert node["term"] == "income support payment"
    assert node["definition_text"] == backfilled.definition_text

    # New defines edge from the section to the new term
    assert graph_with_privacy.graph.has_edge(sec_id, term_id)
    assert graph_with_privacy.graph.edges[sec_id, term_id, "defines"]["type"] == "defines"

    # Node/edge counts grew by exactly one node and one edge, no duplication
    assert graph_with_privacy.graph.number_of_nodes() == nodes_before + 1
    assert graph_with_privacy.graph.number_of_edges() == edges_before + 1

    # Existing act/section nodes untouched
    assert dict(graph_with_privacy.graph.nodes[act_id]) == act_node_before
    assert dict(graph_with_privacy.graph.nodes[sec_id]) == sec_node_before


def test_add_defined_term_classifies_and_creates_mentions_edges():
    act = ActNode(frbr_uri="/akn/au/act/1961/12", title="Sample Registrar Act 1961", year=1961)
    sec_def = SectionNode(
        eid="part-I__sec-5", act_frbr_uri="/akn/au/act/1961/12", heading=None,
        text="Registrar means a person appointed to register marriages.",
    )
    sec_mention = SectionNode(
        eid="part-II__sec-10", act_frbr_uri="/akn/au/act/1961/12", heading=None,
        text="The Registrar must keep a register.",
    )
    data = ActData(act_node=act, sections=[sec_def, sec_mention], defined_terms=[], ref_edges=[])
    g = LexAuGraph()
    g.add_act_data(data)

    backfilled = DefinedTermNode(
        term="registrar", display_term="Registrar",
        act_frbr_uri="/akn/au/act/1961/12", section_eid="part-I__sec-5",
        definition_text="a person appointed to register marriages.",
    )
    g.add_defined_term(backfilled)

    term_id = "/akn/au/act/1961/12#term-registrar"
    sec_mention_id = "/akn/au/act/1961/12#part-II__sec-10"
    assert g.graph.nodes[term_id]["entity_type"] == "registrar"
    assert g.graph.has_edge(sec_mention_id, term_id, key="mentions")
    assert g.graph.edges[sec_mention_id, term_id, "mentions"]["count"] == 1


def test_add_defined_term_non_entity_term_creates_no_mentions_edges():
    act = ActNode(frbr_uri="/akn/au/act/1961/12", title="Sample Registrar Act 1961", year=1961)
    sec_def = SectionNode(
        eid="part-I__sec-5", act_frbr_uri="/akn/au/act/1961/12", heading=None,
        text="purpose means the object for which a thing is done.",
    )
    data = ActData(act_node=act, sections=[sec_def], defined_terms=[], ref_edges=[])
    g = LexAuGraph()
    g.add_act_data(data)

    backfilled = DefinedTermNode(
        term="purpose", display_term="purpose",
        act_frbr_uri="/akn/au/act/1961/12", section_eid="part-I__sec-5",
        definition_text="the object for which a thing is done.",
    )
    g.add_defined_term(backfilled)

    term_id = "/akn/au/act/1961/12#term-purpose"
    assert g.graph.nodes[term_id]["entity_type"] is None
    assert list(g.graph.in_edges(term_id, data=True, keys=True))  # only the 'defines' edge
    mentions_edges = [
        (u, v) for u, v, k, d in g.graph.in_edges(term_id, data=True, keys=True)
        if k == "mentions"
    ]
    assert mentions_edges == []


FOI_INDEX_ENTRY = {
    "name": "Freedom of Information Act 1982",
    "year": 1982,
    "number": 3,
    "effective_date": "2026-06-04",
    "xml_path": "xml/freedom-of-information-act-1982.xml",
}


def test_tagged_cross_act_ref_resolves_once_both_acts_loaded(graph_with_privacy: LexAuGraph):
    # Regression test for the title-normalization bug: before the fix, this citation
    # (ref_text = "the Freedom of Information Act 1982") never resolved because the
    # title-index lookup used raw .lower().strip() instead of normalize_title().
    foi_data = parse_act(FIXTURES / "freedom-of-information-act-1982.xml", FOI_INDEX_ENTRY)
    graph_with_privacy.add_act_data(foi_data)

    src = "/akn/au/act/1988/119#part-I__sec-13"
    tgt = "/akn/au/act/1982/3"
    assert graph_with_privacy.graph.has_edge(src, tgt)
    edge = graph_with_privacy.graph.edges[src, tgt, "ref"]
    assert edge["type"] == "ref"
    assert edge["is_cross_act"] is True


def test_untagged_prose_citation_resolves_when_act_loaded(graph_with_privacy: LexAuGraph):
    foi_data = parse_act(FIXTURES / "freedom-of-information-act-1982.xml", FOI_INDEX_ENTRY)
    graph_with_privacy.add_act_data(foi_data)

    # The untagged sentence added in Task 3: "This section does not limit the Freedom
    # of Information Act 1982." — same section, same target, resolved via matched_title.
    src = "/akn/au/act/1988/119#part-I__sec-13"
    tgt = "/akn/au/act/1982/3"
    assert graph_with_privacy.graph.has_edge(src, tgt)
    assert graph_with_privacy.citation_stats["untagged"]["resolved"] >= 1


def test_unresolved_cross_act_citation_recorded_as_candidate(graph_with_privacy: LexAuGraph):
    # FOI Act is NOT loaded here — both the tagged and untagged citations to it
    # should land in the candidates report, not silently vanish.
    report = graph_with_privacy.citation_candidates_report()
    entry = next(e for e in report if e["title"] == "freedom of information act 1982")
    assert entry["year"] == 1982
    assert entry["mention_count"] == 2  # one tagged + one untagged mention
    assert entry["cited_by"]["/akn/au/act/1988/119"] == 2


def test_self_citation_is_filtered_not_treated_as_candidate():
    g = LexAuGraph()
    act = ActNode(frbr_uri="/akn/au/act/2001/50", title="Corporations Act 2001", year=2001)
    section = SectionNode(
        eid="sec-1", act_frbr_uri=act.frbr_uri, heading=None, text="...", provision_type="section",
    )
    self_ref = RefEdge(
        source_id=section.node_id,
        ref_text="Corporations Act 2001",
        is_cross_act=True,
        target_href=None,
        matched_title="corporations act 2001",
    )
    data = ActData(act_node=act, sections=[section], defined_terms=[], ref_edges=[self_ref])
    g.add_act_data(data)

    assert g.graph.out_degree(section.node_id) == 0
    assert g.citation_stats["untagged"]["self_citation_filtered"] == 1
    assert g.citation_candidates_report() == []


def test_citation_stats_bucket_totals(graph_with_privacy: LexAuGraph):
    stats = graph_with_privacy.citation_stats
    # privacy-act-1988.xml fixture: 1 tagged cross-act citation + 1 untagged, both to FOI.
    assert stats["tagged"]["total"] == 1
    assert stats["untagged"]["total"] == 1


def test_low_confidence_untagged_sample_sorted_shortest_first():
    g = LexAuGraph()
    act = ActNode(frbr_uri="/akn/au/act/2001/50", title="Corporations Act 2001", year=2001)
    section = SectionNode(
        eid="sec-1", act_frbr_uri=act.frbr_uri, heading=None, text="...", provision_type="section",
    )
    refs = [
        RefEdge(
            source_id=section.node_id, ref_text="Fair Work Act 2009", is_cross_act=True,
            target_href=None, matched_title="fair work act 2009",
        ),
        RefEdge(
            source_id=section.node_id, ref_text="Social Security (Administration) Act 1999",
            is_cross_act=True, target_href=None,
            matched_title="social security (administration) act 1999",
        ),
    ]
    data = ActData(act_node=act, sections=[section], defined_terms=[], ref_edges=refs)
    g.add_act_data(data)

    sample = g.low_confidence_untagged_sample(n=1)
    assert sample == ["fair work act 2009"]


def test_intra_act_ref_resolves_via_section_number_index():
    act = ActNode(frbr_uri="/akn/au/act/1999/1", title="Sample Act 1999", year=1999)
    section_6 = SectionNode(eid="part-I__sec-6", act_frbr_uri=act.frbr_uri, heading="Definitions", text="...")
    section_13 = SectionNode(eid="part-I__sec-13", act_frbr_uri=act.frbr_uri, heading="Application", text="...")
    ref = RefEdge(
        source_id=section_13.node_id, ref_text="section 6", is_cross_act=False,
        target_href=None, matched_title=None, matched_section="6",
    )
    data = ActData(act_node=act, sections=[section_6, section_13], defined_terms=[], ref_edges=[ref])

    g = LexAuGraph()
    g.add_act_data(data)

    assert g.graph.has_edge(section_13.node_id, section_6.node_id)
    edge = g.graph.edges[section_13.node_id, section_6.node_id, "ref"]
    assert edge["type"] == "ref"
    assert edge["is_cross_act"] is False


def test_intra_act_ref_to_nonexistent_section_produces_no_edge_not_a_crash():
    act = ActNode(frbr_uri="/akn/au/act/1999/1", title="Sample Act 1999", year=1999)
    section_13 = SectionNode(eid="part-I__sec-13", act_frbr_uri=act.frbr_uri, heading="Application", text="...")
    ref = RefEdge(
        source_id=section_13.node_id, ref_text="section 999", is_cross_act=False,
        target_href=None, matched_title=None, matched_section="999",
    )
    data = ActData(act_node=act, sections=[section_13], defined_terms=[], ref_edges=[ref])

    g = LexAuGraph()
    g.add_act_data(data)  # must not raise

    assert g.graph.out_degree(section_13.node_id) == 0


def test_section_number_index_is_scoped_per_act():
    # Two different Acts each have a "section 6" -- an intra-Act ref in one
    # must never resolve into the other Act's same-numbered section.
    act_a = ActNode(frbr_uri="/akn/au/act/1999/1", title="Sample Act 1999", year=1999)
    act_a_sec_6 = SectionNode(eid="sec-6", act_frbr_uri=act_a.frbr_uri, heading=None, text="...")
    act_a_sec_13 = SectionNode(eid="sec-13", act_frbr_uri=act_a.frbr_uri, heading=None, text="...")
    ref = RefEdge(
        source_id=act_a_sec_13.node_id, ref_text="section 6", is_cross_act=False,
        target_href=None, matched_title=None, matched_section="6",
    )
    data_a = ActData(act_node=act_a, sections=[act_a_sec_6, act_a_sec_13], defined_terms=[], ref_edges=[ref])

    act_b = ActNode(frbr_uri="/akn/au/act/2001/50", title="Other Act 2001", year=2001)
    act_b_sec_6 = SectionNode(eid="sec-6", act_frbr_uri=act_b.frbr_uri, heading=None, text="...")
    data_b = ActData(act_node=act_b, sections=[act_b_sec_6], defined_terms=[], ref_edges=[])

    g = LexAuGraph()
    g.add_act_data(data_a)
    g.add_act_data(data_b)

    assert g.graph.has_edge(act_a_sec_13.node_id, act_a_sec_6.node_id)
    assert not g.graph.has_edge(act_a_sec_13.node_id, act_b_sec_6.node_id)


def test_build_entity_mention_pattern_empty_list_returns_none():
    assert _build_entity_mention_pattern([]) is None


def test_build_entity_mention_pattern_matches_bare_term():
    registrar = DefinedTermNode(
        term="registrar", display_term="Registrar",
        act_frbr_uri="/akn/au/act/1961/12", section_eid="part-I__sec-5",
        definition_text="...", entity_type="registrar",
    )
    pattern = _build_entity_mention_pattern([registrar])
    assert pattern.findall("The Registrar must keep a register.") == ["Registrar"]


def test_build_entity_mention_pattern_no_double_count_registrar_variant():
    # Regression: marriage-act-1961.xml defines both "Registrar" and "the
    # Registrar" as separate DefinedTermNodes. Independent per-term regex
    # matching would produce two matches (one per term) for one real text
    # occurrence of "the Registrar". Longest-first + non-overlapping
    # matching must produce exactly one match, against "the Registrar"'s node.
    registrar = DefinedTermNode(
        term="registrar", display_term="Registrar",
        act_frbr_uri="/akn/au/act/1961/12", section_eid="part-I__sec-5",
        definition_text="...", entity_type="registrar",
    )
    the_registrar = DefinedTermNode(
        term="the_registrar", display_term="the Registrar",
        act_frbr_uri="/akn/au/act/1961/12", section_eid="part-I__sec-6",
        definition_text="...", entity_type="registrar",
    )
    pattern = _build_entity_mention_pattern([registrar, the_registrar])
    matches = pattern.findall("Notice must be given to the Registrar within 14 days.")
    assert matches == ["the Registrar"]


def test_build_entity_mention_pattern_hyphen_compound_no_false_match():
    # Regression: plain \bRegistrar\b treats "-" as a boundary, so it
    # matches inside "Registrar-General". Not live in the corpus today
    # (no Act currently defines both a bare term and its -General
    # compound) but must not silently misfire the moment one does.
    registrar = DefinedTermNode(
        term="registrar", display_term="Registrar",
        act_frbr_uri="/akn/au/act/1961/12", section_eid="part-I__sec-5",
        definition_text="...", entity_type="registrar",
    )
    pattern = _build_entity_mention_pattern([registrar])
    assert pattern.findall("The Registrar-General has no role here.") == []
    assert pattern.findall("Deputy Registrar-General of Marriage Celebrants.") == []


def test_build_entity_mention_pattern_matches_at_string_boundaries():
    registrar = DefinedTermNode(
        term="registrar", display_term="Registrar",
        act_frbr_uri="/akn/au/act/1961/12", section_eid="part-I__sec-5",
        definition_text="...", entity_type="registrar",
    )
    pattern = _build_entity_mention_pattern([registrar])
    assert pattern.findall("Registrar") == ["Registrar"]


def _make_registrar_act_data(mention_text_by_section: dict[str, str]) -> ActData:
    """Build an ActData with one entity-classified DefinedTermNode ("Registrar")
    defined in the first section, and one SectionNode per (eid, text) pair."""
    act = ActNode(frbr_uri="/akn/au/act/1961/12", title="Sample Registrar Act 1961", year=1961)
    sections = [
        SectionNode(eid=eid, act_frbr_uri="/akn/au/act/1961/12", heading=None, text=text)
        for eid, text in mention_text_by_section.items()
    ]
    first_eid = next(iter(mention_text_by_section))
    term = DefinedTermNode(
        term="registrar", display_term="Registrar",
        act_frbr_uri="/akn/au/act/1961/12", section_eid=first_eid,
        definition_text="a person appointed to register marriages.",
        entity_type="registrar",
    )
    return ActData(act_node=act, sections=sections, defined_terms=[term], ref_edges=[])


def test_add_entity_mentions_creates_edge_with_correct_count():
    data = _make_registrar_act_data({
        "part-I__sec-5": "Registrar means a person appointed to register marriages.",
        "part-II__sec-10": "The Registrar must keep a register. The Registrar may delegate this.",
    })
    g = LexAuGraph()
    g.add_act_data(data)

    term_id = "/akn/au/act/1961/12#term-registrar"
    sec5_id = "/akn/au/act/1961/12#part-I__sec-5"
    sec10_id = "/akn/au/act/1961/12#part-II__sec-10"

    assert g.graph.nodes[term_id]["entity_type"] == "registrar"
    assert g.graph.has_edge(sec5_id, term_id, key="mentions")
    assert g.graph.edges[sec5_id, term_id, "mentions"]["count"] == 1
    assert g.graph.has_edge(sec10_id, term_id, key="mentions")
    assert g.graph.edges[sec10_id, term_id, "mentions"]["count"] == 2


def test_add_entity_mentions_no_edge_when_zero_matches():
    data = _make_registrar_act_data({
        "part-I__sec-5": "Registrar means a person appointed to register marriages.",
        "part-III__sec-20": "This section has nothing to do with that office.",
    })
    g = LexAuGraph()
    g.add_act_data(data)

    term_id = "/akn/au/act/1961/12#term-registrar"
    sec20_id = "/akn/au/act/1961/12#part-III__sec-20"
    assert not g.graph.has_edge(sec20_id, term_id, key="mentions")


def test_add_entity_mentions_non_entity_term_gets_no_mentions_edges():
    act = ActNode(frbr_uri="/akn/au/act/1961/12", title="Sample Registrar Act 1961", year=1961)
    section = SectionNode(
        eid="part-I__sec-5", act_frbr_uri="/akn/au/act/1961/12", heading=None,
        text="purpose means the object for which a thing is done.",
    )
    term = DefinedTermNode(
        term="purpose", display_term="purpose",
        act_frbr_uri="/akn/au/act/1961/12", section_eid="part-I__sec-5",
        definition_text="the object for which a thing is done.", entity_type=None,
    )
    data = ActData(act_node=act, sections=[section], defined_terms=[term], ref_edges=[])
    g = LexAuGraph()
    g.add_act_data(data)

    term_id = "/akn/au/act/1961/12#term-purpose"
    sec_id = "/akn/au/act/1961/12#part-I__sec-5"
    assert not g.graph.has_edge(sec_id, term_id, key="mentions")


def test_add_entity_mentions_double_counting_regression():
    # Regression: an Act defining both "Registrar" and "the Registrar" as
    # separate DefinedTermNodes must not produce two mentions edges for one
    # real text occurrence of "the Registrar".
    act = ActNode(frbr_uri="/akn/au/act/1961/12", title="Sample Registrar Act 1961", year=1961)
    sec_def = SectionNode(
        eid="part-I__sec-5", act_frbr_uri="/akn/au/act/1961/12", heading=None,
        text="Registrar means a person appointed to register marriages.",
    )
    sec_qualified_def = SectionNode(
        eid="part-I__sec-6", act_frbr_uri="/akn/au/act/1961/12", heading=None,
        text="the Registrar means the person holding office under section 5.",
    )
    sec_mention = SectionNode(
        eid="part-II__sec-10", act_frbr_uri="/akn/au/act/1961/12", heading=None,
        text="Notice must be given to the Registrar within 14 days.",
    )
    registrar = DefinedTermNode(
        term="registrar", display_term="Registrar",
        act_frbr_uri="/akn/au/act/1961/12", section_eid="part-I__sec-5",
        definition_text="...", entity_type="registrar",
    )
    the_registrar = DefinedTermNode(
        term="the_registrar", display_term="the Registrar",
        act_frbr_uri="/akn/au/act/1961/12", section_eid="part-I__sec-6",
        definition_text="...", entity_type="registrar",
    )
    data = ActData(
        act_node=act, sections=[sec_def, sec_qualified_def, sec_mention],
        defined_terms=[registrar, the_registrar], ref_edges=[],
    )
    g = LexAuGraph()
    g.add_act_data(data)

    registrar_id = "/akn/au/act/1961/12#term-registrar"
    the_registrar_id = "/akn/au/act/1961/12#term-the_registrar"
    sec_mention_id = "/akn/au/act/1961/12#part-II__sec-10"

    assert g.graph.has_edge(sec_mention_id, the_registrar_id, key="mentions")
    assert not g.graph.has_edge(sec_mention_id, registrar_id, key="mentions")


def test_add_entity_mentions_hyphen_compound_regression():
    # Regression: a section mentioning an unrelated hyphenated compound
    # ("Registrar-General") must not produce a mentions edge to the bare
    # "Registrar" entity node.
    act = ActNode(frbr_uri="/akn/au/act/1961/12", title="Sample Registrar Act 1961", year=1961)
    sec_def = SectionNode(
        eid="part-I__sec-5", act_frbr_uri="/akn/au/act/1961/12", heading=None,
        text="Registrar means a person appointed to register marriages.",
    )
    sec_compound = SectionNode(
        eid="part-II__sec-10", act_frbr_uri="/akn/au/act/1961/12", heading=None,
        text="The Registrar-General has no role under this Act.",
    )
    registrar = DefinedTermNode(
        term="registrar", display_term="Registrar",
        act_frbr_uri="/akn/au/act/1961/12", section_eid="part-I__sec-5",
        definition_text="...", entity_type="registrar",
    )
    data = ActData(act_node=act, sections=[sec_def, sec_compound], defined_terms=[registrar], ref_edges=[])
    g = LexAuGraph()
    g.add_act_data(data)

    registrar_id = "/akn/au/act/1961/12#term-registrar"
    sec_compound_id = "/akn/au/act/1961/12#part-II__sec-10"
    assert not g.graph.has_edge(sec_compound_id, registrar_id, key="mentions")
