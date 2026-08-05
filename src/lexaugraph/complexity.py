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


# ALRC's exact word list for Conditional_statements_word_count, per their
# Explanatory Note (alrc.gov.au/wp-content/uploads/2022/12/Explanatory-Note-
# Complexity-and-linguistic-data.pdf, fetched 2026-08-05).
_CONDITIONAL_STATEMENT_WORDS = [
    "if", "except", "but", "provided", "when", "where", "whenever",
    "unless", "notwithstanding",
]
_CONDITIONAL_STATEMENT_PATTERN = re.compile(
    r"\b(?:" + "|".join(_CONDITIONAL_STATEMENT_WORDS) + r")\b", re.IGNORECASE
)

# ALRC has no single "indeterminate concept" list -- five separate word-count
# columns, combined here into one metric. "fair" is deliberately NOT
# left-boundary-anchored, matching ALRC's own 'fair.*' regex which also
# matches inside "unfair" -- preserved for validation fidelity against their
# published numbers, not "fixed".
_INDETERMINATE_CONCEPT_PATTERNS = [
    re.compile(r"reasonabl\w*", re.IGNORECASE),  # Reasonableness_word_count
    re.compile(r"good faith", re.IGNORECASE),    # Good_faith_word_count
    re.compile(r"unfair\w*", re.IGNORECASE),     # Unfair_word_count
    re.compile(r"fair\w*", re.IGNORECASE),       # Fair_word_count
    re.compile(r"unjust\w*", re.IGNORECASE),     # Unjust_word_count
]


def _count_matches(
    section_ids: list[str], graph: nx.MultiDiGraph, pattern: re.Pattern
) -> int:
    return sum(len(pattern.findall(graph.nodes[sid]["text"])) for sid in section_ids)


def _conditional_statement_count(graph: nx.MultiDiGraph, section_ids: list[str]) -> int:
    return _count_matches(section_ids, graph, _CONDITIONAL_STATEMENT_PATTERN)


def _indeterminate_concept_count(graph: nx.MultiDiGraph, section_ids: list[str]) -> int:
    return sum(_count_matches(section_ids, graph, p) for p in _INDETERMINATE_CONCEPT_PATTERNS)


def compute_complexity(
    graph: nx.MultiDiGraph, centrality: dict[str, float]
) -> list[ActComplexity]:
    results: list[ActComplexity] = []
    for node_id, data in graph.nodes(data=True):
        if data.get("type") != "act":
            continue
        act_frbr_uri = node_id
        section_ids = _section_ids(graph, act_frbr_uri)
        node_set = {act_frbr_uri, *section_ids}

        word_count = _word_count(graph, section_ids)
        defined_term_count = _defined_term_count(graph, act_frbr_uri)
        indeterminate_count = _indeterminate_concept_count(graph, section_ids)
        conditional_count = _conditional_statement_count(graph, section_ids)

        results.append(ActComplexity(
            act_frbr_uri=act_frbr_uri,
            title=data.get("title", act_frbr_uri),
            pagerank_centrality=_pagerank_centrality(centrality, [act_frbr_uri, *section_ids]),
            raw_citation_count=_raw_citation_count(graph, node_set),
            defined_term_count=defined_term_count,
            defined_term_density=defined_term_count / word_count if word_count else 0.0,
            indeterminate_concept_count=indeterminate_count,
            indeterminate_concept_density=indeterminate_count / word_count if word_count else 0.0,
            conditional_statement_count=conditional_count,
            conditional_statement_density=conditional_count / word_count if word_count else 0.0,
            word_count=word_count,
        ))
    return results
