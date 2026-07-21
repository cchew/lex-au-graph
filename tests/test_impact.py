from __future__ import annotations
import networkx as nx
import pytest

from lexaugraph.impact import impacted_by, compute_centrality, centrality_percentile


def _add_ref(
    g: nx.MultiDiGraph, u: str, v: str, weight: int = 1, ref_texts: list[str] | None = None
) -> None:
    g.add_edge(u, v, key="ref", type="ref", weight=weight, ref_texts=ref_texts or [f"{u} cites {v}"])


def test_impacted_by_linear_chain_returns_all_citers_within_max_hops():
    # A cites B cites C cites D. Impact of D changing: C (hop1), B (hop2), A (hop3).
    g = nx.MultiDiGraph()
    _add_ref(g, "A", "B")
    _add_ref(g, "B", "C")
    _add_ref(g, "C", "D")

    results = impacted_by(g, "D", max_hops=3)

    by_id = {r.node_id: r for r in results}
    assert set(by_id) == {"A", "B", "C"}
    assert by_id["C"].hop == 1
    assert by_id["B"].hop == 2
    assert by_id["A"].hop == 3


def test_impacted_by_excludes_start_node():
    g = nx.MultiDiGraph()
    _add_ref(g, "A", "B")
    results = impacted_by(g, "B", max_hops=3)
    assert "B" not in {r.node_id for r in results}


def test_impacted_by_max_hops_boundary_exact_included_one_past_excluded():
    g = nx.MultiDiGraph()
    _add_ref(g, "A", "B")
    _add_ref(g, "B", "C")
    _add_ref(g, "C", "D")

    results = impacted_by(g, "D", max_hops=2)

    ids = {r.node_id for r in results}
    assert "B" in ids  # hop 2, exactly at the limit
    assert "A" not in ids  # hop 3, one past the limit


def test_impacted_by_decay_applied_once_per_hop_beyond_the_first():
    g = nx.MultiDiGraph()
    _add_ref(g, "A", "B", weight=2)
    _add_ref(g, "B", "C", weight=3)

    results = impacted_by(g, "C", max_hops=2, decay=0.5)

    by_id = {r.node_id: r for r in results}
    assert by_id["B"].path_weight == pytest.approx(3 * (0.5 ** 0))  # hop 1: no decay
    assert by_id["A"].path_weight == pytest.approx(2 * 3 * (0.5 ** 1))  # hop 2: one decay


def test_impacted_by_no_citers_returns_empty_list():
    g = nx.MultiDiGraph()
    g.add_node("D")
    assert impacted_by(g, "D", max_hops=3) == []


def test_impacted_by_ignores_non_ref_edges():
    g = nx.MultiDiGraph()
    g.add_edge("Act1", "D", key="contains", type="contains")
    assert impacted_by(g, "D", max_hops=3) == []


def test_impacted_by_diamond_picks_max_weight_path():
    # A cites B (weight 2) and C (weight 1); B cites D (weight 3); C cites D (weight 5).
    # Two 2-hop paths to A: via B = 2*3=6, via C = 1*5=5. Max wins: 6 (via B).
    g = nx.MultiDiGraph()
    _add_ref(g, "A", "B", weight=2, ref_texts=["A cites B"])
    _add_ref(g, "A", "C", weight=1, ref_texts=["A cites C"])
    _add_ref(g, "B", "D", weight=3, ref_texts=["B cites D"])
    _add_ref(g, "C", "D", weight=5, ref_texts=["C cites D"])

    results = impacted_by(g, "D", max_hops=2, decay=0.5)

    by_id = {r.node_id: r for r in results}
    assert by_id["A"].hop == 2
    assert by_id["A"].path_weight == pytest.approx(6 * 0.5)
    assert by_id["A"].ref_texts == ["A cites B"]  # winning path's edge, not the losing one


def test_impacted_by_ref_texts_are_the_immediate_citing_edge_not_full_path():
    # For a hop-2 node, ref_texts is the edge closest to that node's own
    # citation into the chain, not the edge nearest the amended section.
    g = nx.MultiDiGraph()
    _add_ref(g, "A", "B", ref_texts=["under subsection 26WD(2)"])
    _add_ref(g, "B", "C", ref_texts=["s 6"])

    results = impacted_by(g, "C", max_hops=2)

    by_id = {r.node_id: r for r in results}
    assert by_id["A"].ref_texts == ["under subsection 26WD(2)"]
    assert by_id["B"].ref_texts == ["s 6"]


def test_impacted_by_cycle_does_not_infinite_loop():
    # A cites B, B cites A (mutual citation), B cites D. Reverse BFS from D
    # must terminate: B (hop1) is visited once and never re-expanded when
    # the A->B edge loops back to it at hop3.
    g = nx.MultiDiGraph()
    _add_ref(g, "A", "B", ref_texts=["A cites B"])
    _add_ref(g, "B", "A", ref_texts=["B cites A"])
    _add_ref(g, "B", "D", ref_texts=["B cites D"])

    results = impacted_by(g, "D", max_hops=5)

    by_id = {r.node_id: r for r in results}
    assert set(by_id) == {"A", "B"}
    assert by_id["B"].hop == 1
    assert by_id["A"].hop == 2


def test_compute_centrality_ranks_heavily_cited_node_above_leaf():
    # HUB and LEAF are both pure sinks (no outgoing edges) so neither's rank
    # drains onward into a downstream funnel -- isolates the in-degree
    # comparison from PageRank's chain-amplification effect on dangling
    # nodes (verified empirically: a HUB with an outgoing edge to LEAF
    # scores *lower* than LEAF, since all of HUB's rank passes through).
    g = nx.MultiDiGraph()
    for citer in ["A", "B", "C"]:
        _add_ref(g, citer, "HUB")
    _add_ref(g, "X", "LEAF")

    scores = compute_centrality(g)

    assert scores["HUB"] > scores["LEAF"]


def test_compute_centrality_is_deterministic():
    g = nx.MultiDiGraph()
    _add_ref(g, "A", "B", weight=2)
    _add_ref(g, "B", "C", weight=1)
    _add_ref(g, "C", "A", weight=3)

    first = compute_centrality(g)
    second = compute_centrality(g)

    assert first == second


def test_compute_centrality_ignores_non_ref_edges():
    g = nx.MultiDiGraph()
    _add_ref(g, "A", "B")
    g.add_edge("Act1", "Sec1", key="contains", type="contains")
    scores = compute_centrality(g)
    assert "A" in scores
    assert "B" in scores
    assert "Act1" not in scores
    assert "Sec1" not in scores


def test_centrality_percentile_ranks_highest_score_at_100():
    scores = {"A": 0.1, "B": 0.5, "C": 0.9}
    assert centrality_percentile(scores, "C") == 100.0


def test_centrality_percentile_ranks_lowest_score_at_0():
    scores = {"A": 0.1, "B": 0.5, "C": 0.9}
    assert centrality_percentile(scores, "A") == 0.0


def test_centrality_percentile_unknown_node_returns_none():
    scores = {"A": 0.1}
    assert centrality_percentile(scores, "unknown") is None


def test_centrality_percentile_single_node_dict_returns_100():
    assert centrality_percentile({"A": 0.5}, "A") == 100.0
