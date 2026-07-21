from __future__ import annotations
import networkx as nx

from .models import ImpactedNode


def impacted_by(
    graph: nx.MultiDiGraph, node_id: str, max_hops: int = 3, decay: float = 0.5
) -> list[ImpactedNode]:
    """Reverse-reachability BFS over 'ref' edges: everything that transitively
    cites node_id, within max_hops. This is fan-in (what depends on node_id),
    not fan-out (what node_id itself cites) -- answers "what's affected if
    node_id changes."

    When multiple shortest paths of the same hop count reach a node (a
    diamond pattern), the path with the highest raw weight product wins --
    both for path_weight and for which edge's ref_texts are reported.
    """
    reversed_graph = graph.reverse(copy=False)
    visited_hop: dict[str, int] = {node_id: 0}
    raw_weight: dict[str, float] = {node_id: 1.0}
    ref_texts: dict[str, list[str]] = {}
    ordered: list[str] = []

    frontier = [node_id]
    for hop in range(1, max_hops + 1):
        candidates: dict[str, tuple[float, list[str]]] = {}
        for current in frontier:
            for _, neighbor, data in reversed_graph.out_edges(current, data=True):
                if data.get("type") != "ref" or neighbor in visited_hop:
                    continue
                candidate_raw = raw_weight[current] * data.get("weight", 1)
                best = candidates.get(neighbor)
                if best is None or candidate_raw > best[0]:
                    candidates[neighbor] = (candidate_raw, data.get("ref_texts", []))

        next_frontier = []
        for neighbor, (candidate_raw, candidate_ref_texts) in candidates.items():
            visited_hop[neighbor] = hop
            raw_weight[neighbor] = candidate_raw
            ref_texts[neighbor] = candidate_ref_texts
            ordered.append(neighbor)
            next_frontier.append(neighbor)
        frontier = next_frontier
        if not frontier:
            break

    return [
        ImpactedNode(
            node_id=n,
            hop=visited_hop[n],
            path_weight=raw_weight[n] * (decay ** (visited_hop[n] - 1)),
            ref_texts=ref_texts[n],
        )
        for n in ordered
    ]


def compute_centrality(graph: nx.MultiDiGraph) -> dict[str, float]:
    """PageRank over the 'ref'-edge subgraph, weighted by citation frequency.

    A static, whole-graph structural-importance ranking -- complementary to
    impacted_by()'s per-node blast-radius query, not a substitute for it.
    Precompute once via 'lexaugraph centrality', not per-query.
    """
    subgraph = nx.MultiDiGraph()
    for u, v, data in graph.edges(data=True):
        if data.get("type") == "ref":
            subgraph.add_edge(u, v, weight=data.get("weight", 1))
    if subgraph.number_of_edges() == 0:
        return {}
    return nx.pagerank(subgraph, weight="weight")
