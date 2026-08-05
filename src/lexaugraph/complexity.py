from __future__ import annotations
import re
import networkx as nx

from .models import ActComplexity


def _section_ids(graph: nx.MultiDiGraph, act_frbr_uri: str) -> list[str]:
    """All Section node ids contained directly under an Act, via 'contains' edges."""
    return [
        target for _, target, data in graph.out_edges(act_frbr_uri, data=True)
        if data.get("type") == "contains"
    ]


def _raw_citation_count(graph: nx.MultiDiGraph, node_set: set[str]) -> int:
    """Distinct 'ref' edges with at least one endpoint in node_set.

    Not sum(in-edges) + sum(out-edges) -- that double-counts every intra-Act
    citation (both endpoints inside node_set), inflating the true count.
    Verified against real Privacy Act 1988 data during spec review: naive
    in+out summing inflated the count ~22% (1,197 vs. 939 distinct edges).
    """
    count = 0
    for u, v, data in graph.edges(data=True):
        if data.get("type") != "ref":
            continue
        if u in node_set or v in node_set:
            count += 1
    return count


def _pagerank_centrality(centrality: dict[str, float], node_ids: list[str]) -> float:
    """Sum of PageRank scores across an Act's own node id plus all its Section
    node ids. centrality.json is per-node, not pre-aggregated to Act level:
    cross-Act citations resolved only by title target the Act node directly;
    intra-Act and anchor-resolved cross-Act citations target a Section node.
    """
    return sum(centrality.get(nid, 0.0) for nid in node_ids)


def _defined_term_count(graph: nx.MultiDiGraph, act_frbr_uri: str) -> int:
    return sum(
        1 for _, data in graph.nodes(data=True)
        if data.get("type") == "defined_term" and data.get("act_frbr_uri") == act_frbr_uri
    )


def _word_count(graph: nx.MultiDiGraph, section_ids: list[str]) -> int:
    return sum(len(graph.nodes[sid]["text"].split()) for sid in section_ids)
