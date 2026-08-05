from __future__ import annotations
import networkx as nx
import pytest

from lexaugraph.complexity import _section_ids, _raw_citation_count, _pagerank_centrality


def _base_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    g.add_node("/akn/au/act/2000/1", type="act", title="Test Act 2000")
    g.add_node(
        "/akn/au/act/2000/1#sec-1", type="section",
        act_frbr_uri="/akn/au/act/2000/1", text="",
    )
    g.add_node(
        "/akn/au/act/2000/1#sec-2", type="section",
        act_frbr_uri="/akn/au/act/2000/1", text="",
    )
    g.add_edge("/akn/au/act/2000/1", "/akn/au/act/2000/1#sec-1", key="contains", type="contains")
    g.add_edge("/akn/au/act/2000/1", "/akn/au/act/2000/1#sec-2", key="contains", type="contains")
    return g


def test_section_ids_returns_all_sections_under_act():
    g = _base_graph()
    ids = _section_ids(g, "/akn/au/act/2000/1")
    assert set(ids) == {"/akn/au/act/2000/1#sec-1", "/akn/au/act/2000/1#sec-2"}


def test_section_ids_ignores_other_acts_sections():
    g = _base_graph()
    g.add_node("/akn/au/act/1999/9", type="act", title="Other Act 1999")
    g.add_node("/akn/au/act/1999/9#sec-1", type="section", act_frbr_uri="/akn/au/act/1999/9", text="")
    g.add_edge("/akn/au/act/1999/9", "/akn/au/act/1999/9#sec-1", key="contains", type="contains")
    ids = _section_ids(g, "/akn/au/act/2000/1")
    assert "/akn/au/act/1999/9#sec-1" not in ids


def test_raw_citation_count_does_not_double_count_intra_act_citation():
    g = _base_graph()
    g.add_edge(
        "/akn/au/act/2000/1#sec-1", "/akn/au/act/2000/1#sec-2",
        key="ref", type="ref", citations=[{"ref_text": "s 2"}],
    )
    node_set = {
        "/akn/au/act/2000/1", "/akn/au/act/2000/1#sec-1", "/akn/au/act/2000/1#sec-2",
    }
    # Both endpoints of this ref edge are inside node_set -- must count once, not
    # twice (the bug an in-edges + out-edges sum would introduce).
    assert _raw_citation_count(g, node_set) == 1


def test_raw_citation_count_counts_cross_act_citation_once():
    g = _base_graph()
    g.add_node("/akn/au/act/1999/9", type="act", title="Other Act 1999")
    g.add_edge(
        "/akn/au/act/2000/1#sec-1", "/akn/au/act/1999/9",
        key="ref", type="ref", citations=[{"ref_text": "the Other Act 1999"}],
    )
    node_set = {
        "/akn/au/act/2000/1", "/akn/au/act/2000/1#sec-1", "/akn/au/act/2000/1#sec-2",
    }
    assert _raw_citation_count(g, node_set) == 1


def test_raw_citation_count_ignores_non_ref_edges():
    g = _base_graph()
    node_set = {
        "/akn/au/act/2000/1", "/akn/au/act/2000/1#sec-1", "/akn/au/act/2000/1#sec-2",
    }
    assert _raw_citation_count(g, node_set) == 0


def test_pagerank_centrality_sums_across_act_and_section_nodes():
    centrality = {
        "/akn/au/act/2000/1": 0.01,
        "/akn/au/act/2000/1#sec-1": 0.02,
        # sec-2 deliberately absent -- nodes with no ref edges never enter
        # PageRank's subgraph, must default to 0.0 not raise KeyError.
    }
    node_ids = [
        "/akn/au/act/2000/1", "/akn/au/act/2000/1#sec-1", "/akn/au/act/2000/1#sec-2",
    ]
    assert _pagerank_centrality(centrality, node_ids) == pytest.approx(0.03)


from lexaugraph.complexity import _defined_term_count, _word_count  # noqa: E402


def test_defined_term_count_counts_only_this_acts_terms():
    g = _base_graph()
    g.add_node(
        "/akn/au/act/2000/1#term-x", type="defined_term",
        act_frbr_uri="/akn/au/act/2000/1",
    )
    g.add_node(
        "/akn/au/act/1999/9#term-y", type="defined_term",
        act_frbr_uri="/akn/au/act/1999/9",
    )
    assert _defined_term_count(g, "/akn/au/act/2000/1") == 1


def test_defined_term_count_zero_when_none_defined():
    g = _base_graph()
    assert _defined_term_count(g, "/akn/au/act/2000/1") == 0


def test_word_count_sums_section_text_word_counts():
    g = nx.MultiDiGraph()
    g.add_node("/akn/au/act/2000/1", type="act", title="Test Act 2000")
    g.add_node(
        "/akn/au/act/2000/1#sec-1", type="section",
        act_frbr_uri="/akn/au/act/2000/1", text="one two three",
    )
    g.add_node(
        "/akn/au/act/2000/1#sec-2", type="section",
        act_frbr_uri="/akn/au/act/2000/1", text="four five",
    )
    section_ids = ["/akn/au/act/2000/1#sec-1", "/akn/au/act/2000/1#sec-2"]
    assert _word_count(g, section_ids) == 5


def test_word_count_empty_section_list_returns_zero():
    g = _base_graph()
    assert _word_count(g, []) == 0


from lexaugraph.complexity import (  # noqa: E402
    _conditional_statement_count,
    _indeterminate_concept_count,
)


def test_conditional_statement_count_matches_alrc_word_list():
    g = nx.MultiDiGraph()
    text = (
        "If a person applies, the Secretary may grant approval unless the "
        "application is incomplete."
    )
    g.add_node("/akn/au/act/2000/1#sec-1", type="section", act_frbr_uri="/akn/au/act/2000/1", text=text)
    count = _conditional_statement_count(g, ["/akn/au/act/2000/1#sec-1"])
    assert count == 2  # "If" (case-insensitive) + "unless"


def test_conditional_statement_count_zero_when_no_matches():
    g = nx.MultiDiGraph()
    g.add_node(
        "/akn/au/act/2000/1#sec-1", type="section",
        act_frbr_uri="/akn/au/act/2000/1", text="The Secretary is appointed.",
    )
    assert _conditional_statement_count(g, ["/akn/au/act/2000/1#sec-1"]) == 0


def test_indeterminate_concept_count_sums_all_five_alrc_patterns():
    g = nx.MultiDiGraph()
    text = (
        "The Secretary must act reasonably and in good faith, and must not "
        "act unfairly."
    )
    g.add_node("/akn/au/act/2000/1#sec-1", type="section", act_frbr_uri="/akn/au/act/2000/1", text=text)
    count = _indeterminate_concept_count(g, ["/akn/au/act/2000/1#sec-1"])
    # reasonabl\w* -> "reasonably" (1); good faith -> "good faith" (1);
    # unfair\w* -> "unfairly" (1); fair\w* -> "fairly" inside "unfairly" too,
    # per ALRC's own unanchored pattern (1); unjust\w* -> no match (0). Total 4.
    assert count == 4


def test_indeterminate_concept_count_zero_when_no_matches():
    g = nx.MultiDiGraph()
    g.add_node(
        "/akn/au/act/2000/1#sec-1", type="section",
        act_frbr_uri="/akn/au/act/2000/1", text="The Secretary is appointed.",
    )
    assert _indeterminate_concept_count(g, ["/akn/au/act/2000/1#sec-1"]) == 0
