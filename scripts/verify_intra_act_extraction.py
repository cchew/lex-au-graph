"""One-off verification: rebuild the graph from the real lex-au corpus and
confirm (a) intra-Act ref edge count substantially increases over the
pre-fix baseline (2,186 — see the design spec's Motivation), and (b) the
weight fix is visible on repeated citations. Also prints a low-confidence
sample of intra-Act matches for manual eyeballing, the same way
low_confidence_untagged_sample does for the cross-Act path.
"""
from pathlib import Path

from lexaugraph.graph import LexAuGraph

CORPUS_DIR = Path("../../lex-au/repo/corpus/")
BASELINE_INTRA_ACT_EDGES = 2186


def main() -> None:
    g = LexAuGraph()
    g.build(CORPUS_DIR)

    intra_act_edges = [
        (u, v, d) for u, v, d in g.graph.edges(data=True)
        if d.get("type") == "ref" and d.get("is_cross_act") is False
    ]
    print(f"Intra-Act ref edges: {len(intra_act_edges)} (baseline: {BASELINE_INTRA_ACT_EDGES})")
    if len(intra_act_edges) <= BASELINE_INTRA_ACT_EDGES:
        print("WARNING: no increase over baseline -- extraction fix may not be wired in.")

    weighted = [e for e in intra_act_edges if e[2].get("weight", 1) > 1]
    print(f"Intra-Act edges with weight > 1 (repeated citations): {len(weighted)}")

    print()
    print("Top 10 intra-Act edges by weight (sanity check the weight fix is live):")
    for u, v, d in sorted(intra_act_edges, key=lambda e: -e[2].get("weight", 1))[:10]:
        print(f"  {u} -> {v}  weight={d.get('weight', 1)}  ref_texts={d.get('ref_texts', [d.get('ref_text')])}")

    print()
    print("Shortest ref_text samples (most likely false positives, for manual eyeballing):")
    all_ref_texts = [rt for _, _, d in intra_act_edges for rt in d.get("ref_texts", [d.get("ref_text")])]
    for rt in sorted(all_ref_texts, key=len)[:10]:
        print(f"  - {rt}")


if __name__ == "__main__":
    main()
