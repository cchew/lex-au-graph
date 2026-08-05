"""Validate signal 3 (prescriptive-language density) against two real external
sources: ALRC DataHub's "In force Acts - Complexity and linguistic data" Excel
export (Obligations_word_count column, 7-word list) and RegData Australia's own
downloadable dataset (RDAU1.0, 5-word subset).

Gates nothing automatically -- same posture as complexity's own ALRC validation
(scripts/complexity_validation_pilot.py): no fixed go/no-go threshold, Ching
reviews the correlation numbers and decides whether the live signal is trustworthy.

Usage:
    pip install pandas openpyxl  # not a project dependency, one-off tool only
    python scripts/codifiability_validation_pilot.py \
        --alrc-excel path/to/in-force-acts-complexity-and-linguistic-data.xlsx \
        --graph graph.json \
        --output codifiability_validation_results.json

Both source Excel exports must be downloaded manually first (public downloads,
not fetched by this script) -- see alrc.gov.au/datahub/download-the-data/ and
the RegData Australia / QuantGov download page for RDAU1.0.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import pandas as pd
from scipy.stats import pearsonr, spearmanr

from lexaugraph.citations import normalize_title
from lexaugraph.codifiability import _PRESCRIPTIVE_DENSITY_PATTERN_7, _PRESCRIPTIVE_DENSITY_PATTERN_5
from lexaugraph.complexity import _section_ids, _count_matches
from lexaugraph.graph import LexAuGraph


def match_acts(source_df: pd.DataFrame, graph: LexAuGraph) -> dict[int, str]:
    """Map a source DataFrame's row index -> live corpus Act FRBR URI, by
    normalized title match (identical approach to complexity's own validation)."""
    title_to_frbr: dict[str, str] = {}
    for node_id, data in graph.graph.nodes(data=True):
        if data.get("type") == "act" and data.get("title"):
            normalized = normalize_title(data["title"])
            if normalized:
                title_to_frbr[normalized[0]] = node_id

    matches: dict[int, str] = {}
    for idx, row in source_df.iterrows():
        normalized = normalize_title(str(row.get("title", "")))
        if normalized and normalized[0] in title_to_frbr:
            matches[idx] = title_to_frbr[normalized[0]]
    return matches


def compute_live_density(graph: LexAuGraph, act_frbr_uri: str) -> dict[str, int]:
    section_ids = _section_ids(graph.graph, act_frbr_uri)
    return {
        "obligations_7word": _count_matches(section_ids, graph.graph, _PRESCRIPTIVE_DENSITY_PATTERN_7),
        "regdata_5word": _count_matches(section_ids, graph.graph, _PRESCRIPTIVE_DENSITY_PATTERN_5),
    }


def correlate(a: list[float], b: list[float]) -> dict[str, float | int]:
    pearson_r, _ = pearsonr(a, b)
    spearman_r, _ = spearmanr(a, b)
    return {"pearson": pearson_r, "spearman": spearman_r, "n": len(a)}


def run_validation(alrc_df: pd.DataFrame, graph: LexAuGraph) -> dict:
    matches = match_acts(alrc_df, graph)
    result = {"matched_acts": len(matches)}

    if "Obligations_word_count" not in alrc_df.columns:
        result["obligations_7word_vs_alrc"] = {
            "pearson": None,
            "spearman": None,
            "n": 0,
            "note": "Obligations_word_count column not found in ALRC export",
        }
        result["live_regdata_5word_total"] = None
    else:
        alrc_values: list[float] = []
        live_values: list[float] = []
        regdata_5word_total = 0
        for idx, act_frbr_uri in matches.items():
            live = compute_live_density(graph, act_frbr_uri)
            alrc_values.append(float(alrc_df.loc[idx, "Obligations_word_count"]))
            live_values.append(float(live["obligations_7word"]))
            regdata_5word_total += live["regdata_5word"]

        if len(alrc_values) >= 2:
            result["obligations_7word_vs_alrc"] = correlate(alrc_values, live_values)
        else:
            result["obligations_7word_vs_alrc"] = {"pearson": None, "spearman": None, "n": len(alrc_values)}
        result["live_regdata_5word_total"] = regdata_5word_total

    result["note"] = (
        "RDAU1.0 (RegData Australia's own 5-word dataset) cross-correlation requires a "
        "second downloaded dataset, not automated by this script -- run manually with "
        "the same match_acts/compute_live_density helpers against RDAU1.0's export once "
        "downloaded. live_regdata_5word_total is the live corpus's 5-word count summed "
        "across matched Acts, computed here for reuse by that manual step."
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alrc-excel", type=Path, required=True)
    parser.add_argument("--graph", type=Path, default=Path("graph.json"))
    parser.add_argument("--output", type=Path, default=Path("codifiability_validation_results.json"))
    args = parser.parse_args()

    alrc_df = pd.read_excel(args.alrc_excel)
    graph = LexAuGraph.load(args.graph)
    results = run_validation(alrc_df, graph)

    args.output.write_text(json.dumps(results, indent=2))
    print(f"Matched {results['matched_acts']} Acts against ALRC's Dec-2022 export.")
    print(results["obligations_7word_vs_alrc"])
    print(f"  live_regdata_5word_total={results['live_regdata_5word_total']}")


if __name__ == "__main__":
    main()
