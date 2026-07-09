from pathlib import Path
import pytest
from lexaugraph.graph import LexAuGraph
from lexaugraph.loader import parse_act
from lexaugraph.models import ActData, DefinedTermNode

FIXTURES = Path(__file__).parent / "fixtures"
INDEX_ENTRY = {
    "name": "Privacy Act 1988",
    "year": 1988,
    "number": 119,
    "effective_date": "2026-06-04",
    "xml_path": "xml/privacy-act-1988.xml",
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
    edge = graph_with_privacy.graph.edges[act_id, sec_id]
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
    edge = graph_with_privacy.graph.edges[sec_id, term_id]
    assert edge["type"] == "defines"


def test_same_act_ref_edge(graph_with_privacy: LexAuGraph):
    src = "/akn/au/act/1988/119#part-I__sec-13"
    tgt = "/akn/au/act/1988/119#part-I__sec-6"
    assert graph_with_privacy.graph.has_edge(src, tgt)
    edge = graph_with_privacy.graph.edges[src, tgt]
    assert edge["type"] == "ref"


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
    assert loaded.graph.number_of_nodes() == graph_with_privacy.graph.number_of_nodes()
    assert loaded.graph.number_of_edges() == graph_with_privacy.graph.number_of_edges()
    # Act node survives roundtrip
    assert "/akn/au/act/1988/119" in loaded.graph.nodes


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
    assert graph_with_privacy.graph.edges[sec_id, term_id]["type"] == "defines"

    # Node/edge counts grew by exactly one node and one edge, no duplication
    assert graph_with_privacy.graph.number_of_nodes() == nodes_before + 1
    assert graph_with_privacy.graph.number_of_edges() == edges_before + 1

    # Existing act/section nodes untouched
    assert dict(graph_with_privacy.graph.nodes[act_id]) == act_node_before
    assert dict(graph_with_privacy.graph.nodes[sec_id]) == sec_node_before
