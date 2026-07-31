"""One-off verification: rebuild the graph from the real lex-au corpus and sample
classified ref citations per relation type, for manual eyeballing against real Act
text.

A clean test suite does not confirm real-corpus classification accuracy -- this
script exists specifically to catch cases where the regex verb-proximity window
misfires on real legislative phrasing the unit tests didn't anticipate. Given the
corrected yield finding (56% of corpus files are standalone Amendment Acts), expect
non-trivial volume in all four relation types, not just cites/references_definition.
"""
from collections import Counter
from pathlib import Path

from lexaugraph.graph import LexAuGraph

CORPUS_DIR = Path("../../lex-au/repo/corpus/")
SAMPLE_SIZE_PER_RELATION = 10


def main() -> None:
    g = LexAuGraph()
    g.build(CORPUS_DIR)  # regex-only classification -- pass client= via a modified
                          # copy of this script if you need to sample LLM-fallback output too

    relation_counts: Counter[str] = Counter()
    samples: dict[str, list[tuple[str, str, str]]] = {}
    for u, v, data in g.graph.edges(data=True):
        if data.get("type") != "ref":
            continue
        for citation in data.get("citations", []):
            relation = citation["relation"]
            relation_counts[relation] += 1
            bucket = samples.setdefault(relation, [])
            if len(bucket) < SAMPLE_SIZE_PER_RELATION:
                bucket.append((u, v, citation["ref_text"]))

    print("Relation type distribution:")
    for relation, count in relation_counts.most_common():
        print(f"  {relation}: {count}")

    for relation, examples in samples.items():
        print()
        print(f"Sample '{relation}' citations (eyeball against real Act text):")
        for u, v, ref_text in examples:
            print(f'  {u} -> {v}  ref_text="{ref_text}"')


if __name__ == "__main__":
    main()
