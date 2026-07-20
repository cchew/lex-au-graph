from __future__ import annotations
import networkx as nx
import pytest

from lexaugraph.impact import impacted_by


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
