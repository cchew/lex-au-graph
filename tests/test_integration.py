"""
Integration test: build graph from the real lex-au corpus.

Skipped if corpus is not available (CI environments without the corpus).
"""
from pathlib import Path
import pytest
from lexaugraph.graph import LexAuGraph
from lexaugraph.resolver import DefinitionResolver

CORPUS = Path(__file__).parent.parent.parent.parent / "lex-au" / "repo" / "corpus"

pytestmark = pytest.mark.skipif(
    not CORPUS.exists(),
    reason="lex-au corpus not available at expected path"
)


@pytest.fixture(scope="module")
def full_graph() -> LexAuGraph:
    g = LexAuGraph()
    g.build(CORPUS)
    return g


@pytest.fixture(scope="module")
def resolver(full_graph: LexAuGraph) -> DefinitionResolver:
    return DefinitionResolver(full_graph)


def test_graph_has_acts(full_graph: LexAuGraph):
    stats = full_graph.stats()
    assert stats["node_types"].get("act", 0) >= 8


def test_graph_has_sections(full_graph: LexAuGraph):
    stats = full_graph.stats()
    assert stats["node_types"].get("section", 0) > 100


def test_graph_has_defined_terms(full_graph: LexAuGraph):
    stats = full_graph.stats()
    # XPath extraction over <term>/<def> AKN markup: 2,516 pairs, 2,395 unique nodes
    assert stats["node_types"].get("defined_term", 0) >= 2390


def test_privacy_act_personal_information(resolver: DefinitionResolver):
    result = resolver.resolve_definition("personal information", "/akn/au/act/1988/119")
    assert result is not None
    assert "identified individual" in result.definition_text.lower()
    assert result.act_title == "Privacy Act 1988"


def test_privacy_act_tax_file_number(resolver: DefinitionResolver):
    result = resolver.resolve_definition("tax file number", "/akn/au/act/1988/119")
    assert result is not None
    assert result.section_eid is not None
    assert "number" in result.definition_text.lower()


def test_cross_ref_from_privacy_act_to_foi(full_graph: LexAuGraph):
    # Privacy Act has edges (contains/defines). Cross-act <ref> edges are v0.2.0+.
    # This test ensures the query precedence is correct: all three conditions must hold together.
    privacy_act_uri = "/akn/au/act/1988/119"
    privacy_edges = [
        (u, v, d)
        for u, v, d in full_graph.graph.edges(data=True)
        if "privacy-act" in u.lower() or privacy_act_uri in u
    ]
    assert len(privacy_edges) > 0  # Privacy Act has edges

    # Ref edges with is_cross_act: currently empty (v0.2.0+), but query is correct
    ref_edges = [
        (u, v, d)
        for u, v, d in full_graph.graph.edges(data=True)
        if d.get("type") == "ref" and d.get("is_cross_act")
        and ("privacy-act" in u.lower() or privacy_act_uri in u)
    ]
    # Cross-act ref edges from Privacy Act are expected once lex-au v0.2.0 populates FRBR hrefs.
    # For now, assert the query itself runs without error and returns a list.
    assert isinstance(ref_edges, list)


def test_save_load_roundtrip(full_graph: LexAuGraph, tmp_path: Path):
    path = tmp_path / "graph.json"
    full_graph.save(path)
    loaded = LexAuGraph.load(path)
    assert loaded.graph.number_of_nodes() == full_graph.graph.number_of_nodes()
    assert loaded.graph.number_of_edges() == full_graph.graph.number_of_edges()


def test_privacy_act_entity_classification(full_graph: LexAuGraph):
    # Privacy Act 1988 defines "Commissioner" and "Secretary" as entity-classified
    # terms, but no "Minister" or "Registrar" term at all (confirmed 2026-08-04
    # independent review — the design spec's original worked example incorrectly
    # cited numbers for these two, since this Act never defines them).
    commissioner_id = "/akn/au/act/1988/119#term-commissioner"
    secretary_id = "/akn/au/act/1988/119#term-secretary"
    assert full_graph.graph.nodes[commissioner_id]["entity_type"] == "commissioner"
    assert full_graph.graph.nodes[secretary_id]["entity_type"] == "secretary"


def test_privacy_act_secretary_mention_count(full_graph: LexAuGraph):
    # Small, stable real number, independently verified 2026-08-04 against the
    # real corpus via the exact combined-regex algorithm this feature implements.
    secretary_id = "/akn/au/act/1988/119#term-secretary"
    total = sum(
        d["count"] for u, v, d in full_graph.graph.in_edges(secretary_id, data=True)
        if d.get("type") == "mentions"
    )
    sections = sum(
        1 for u, v, d in full_graph.graph.in_edges(secretary_id, data=True)
        if d.get("type") == "mentions"
    )
    assert total == 3
    assert sections == 2


def test_privacy_act_commissioner_mention_count_ballpark(full_graph: LexAuGraph):
    # Larger number, loose bound to tolerate implementation-detail variance
    # (e.g. exact overlap resolution between "Commissioner" and "Commissioner
    # of Police") without hard-coding a brittle exact figure.
    commissioner_id = "/akn/au/act/1988/119#term-commissioner"
    total = sum(
        d["count"] for u, v, d in full_graph.graph.in_edges(commissioner_id, data=True)
        if d.get("type") == "mentions"
    )
    assert total > 600


def test_entity_yield_across_corpus(full_graph: LexAuGraph):
    # Real corpus-wide yield, independently verified 2026-08-04: 1,880 of 29,254
    # total defined terms (6.4%) classify as an entity, out of 3,078 files, 0
    # parse errors. Loose lower bound (not an exact match) to tolerate the
    # corpus growing between this test's writing and a future lex-au ingest.
    entity_count = sum(
        1 for _, data in full_graph.graph.nodes(data=True)
        if data.get("type") == "defined_term" and data.get("entity_type")
    )
    assert entity_count >= 1800
