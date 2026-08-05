"""Validate complexity.py's metrics against ALRC DataHub's frozen Dec-2022
"In force Acts - Complexity and linguistic data" export
(alrc.gov.au/datahub/download-the-data/).

Gates nothing automatically -- per
docs/superpowers/specs/2026-08-05-structural-complexity-design.md's
Validation section, there is no fixed go/no-go correlation threshold.
ALRC's own methodology is itself unvalidated in the literature, so
disagreement here is ambiguous (could be a build bug, or genuine
corpus-drift since ALRC's Dec-2022 freeze). Ching reviews the output and
decides whether to trust the live numbers, then writes up the results in
the same publication-ready style as docs/2026-08-05-vago-pilot-results.md.

Usage:
    pip install pandas openpyxl  # not a project dependency, one-off tool only
    python scripts/complexity_validation_pilot.py \
        --alrc-excel path/to/in-force-acts-complexity-and-linguistic-data.xlsx \
        --graph graph.json \
        --output complexity_validation_results.json

The ALRC Excel export must be downloaded manually first (public download,
not fetched by this script) -- see alrc.gov.au/datahub/download-the-data/.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import pandas as pd
from scipy.stats import pearsonr, spearmanr

from lexaugraph.citations import normalize_title
from lexaugraph.complexity import (
    _CONDITIONAL_STATEMENT_PATTERN,
    _INDETERMINATE_CONCEPT_PATTERNS,
    _count_matches,
    _section_ids,
)
from lexaugraph.graph import LexAuGraph

# ALRC Excel column name -> the one of our five indeterminate-concept
# sub-patterns it corresponds to (see complexity.py's _INDETERMINATE_CONCEPT_PATTERNS,
# same order: reasonableness, good faith, unfair, fair, unjust).
_ALRC_SUBPATTERN_COLUMNS = dict(zip(
    [
        "Reasonableness_word_count", "Good_faith_word_count", "Unfair_word_count",
        "Fair_word_count", "Unjust_word_count",
    ],
    _INDETERMINATE_CONCEPT_PATTERNS,
))


def match_acts(alrc_df: pd.DataFrame, graph: LexAuGraph) -> dict[int, str]:
    """Map ALRC DataFrame row index -> live corpus Act FRBR URI, by normalized title."""
    title_to_frbr: dict[str, str] = {}
    for node_id, data in graph.graph.nodes(data=True):
        if data.get("type") == "act" and data.get("title"):
            normalized = normalize_title(data["title"])
            if normalized:
                title_to_frbr[normalized[0]] = node_id

    matches: dict[int, str] = {}
    for idx, row in alrc_df.iterrows():
        normalized = normalize_title(str(row.get("title", "")))
        if normalized and normalized[0] in title_to_frbr:
            matches[idx] = title_to_frbr[normalized[0]]
    return matches


def compute_live_counts(graph: LexAuGraph, act_frbr_uri: str) -> dict[str, int]:
    section_ids = _section_ids(graph.graph, act_frbr_uri)
    counts = {
        "Conditional_statements_word_count": _count_matches(
            section_ids, graph.graph, _CONDITIONAL_STATEMENT_PATTERN
        ),
    }
    for column, pattern in _ALRC_SUBPATTERN_COLUMNS.items():
        counts[column] = _count_matches(section_ids, graph.graph, pattern)
    return counts


def correlate(alrc_values: list[float], live_values: list[float]) -> dict[str, float | int]:
    pearson_r, _ = pearsonr(alrc_values, live_values)
    spearman_r, _ = spearmanr(alrc_values, live_values)
    return {"pearson": pearson_r, "spearman": spearman_r, "n": len(alrc_values)}


def run_validation(alrc_df: pd.DataFrame, graph: LexAuGraph) -> dict:
    matches = match_acts(alrc_df, graph)
    columns = ["Conditional_statements_word_count", *_ALRC_SUBPATTERN_COLUMNS.keys()]
    results: dict[str, dict] = {}
    for column in columns:
        if column not in alrc_df.columns:
            results[column] = {"pearson": None, "spearman": None, "n": 0, "note": "column not in ALRC export"}
            continue
        alrc_values: list[float] = []
        live_values: list[float] = []
        for idx, act_frbr_uri in matches.items():
            live_counts = compute_live_counts(graph, act_frbr_uri)
            alrc_values.append(float(alrc_df.loc[idx, column]))
            live_values.append(float(live_counts[column]))
        if len(alrc_values) >= 2:
            results[column] = correlate(alrc_values, live_values)
        else:
            results[column] = {"pearson": None, "spearman": None, "n": len(alrc_values)}
    return {"matched_acts": len(matches), "metrics": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alrc-excel", type=Path, required=True)
    parser.add_argument("--graph", type=Path, default=Path("graph.json"))
    parser.add_argument("--output", type=Path, default=Path("complexity_validation_results.json"))
    args = parser.parse_args()

    alrc_df = pd.read_excel(args.alrc_excel)
    graph = LexAuGraph.load(args.graph)
    results = run_validation(alrc_df, graph)

    args.output.write_text(json.dumps(results, indent=2))
    print(f"Matched {results['matched_acts']} Acts against ALRC's Dec-2022 export.")
    for column, stats in results["metrics"].items():
        print(f"  {column}: pearson={stats['pearson']}, spearman={stats['spearman']}, n={stats['n']}")


if __name__ == "__main__":
    main()
