"""One-off verification: rebuild the graph from the (already-fixed) lex-au
corpus and confirm every previously-colliding term slug now survives as
multiple distinct nodes, queryable via find_all_definitions.
"""
from pathlib import Path
from lexaugraph.graph import LexAuGraph
from lexaugraph.resolver import DefinitionResolver

CORPUS_DIR = Path("/Users/chingchew/Documents/Claude/Code/executive-assistant/projects/lex-au/repo/corpus")


def main() -> None:
    g = LexAuGraph()
    g.build(CORPUS_DIR)

    resolver = DefinitionResolver(g)

    slug_counts: dict[tuple[str, str], int] = {}
    for node_id, data in g.graph.nodes(data=True):
        if data.get("type") != "defined_term":
            continue
        key = (data.get("act_frbr_uri", ""), data.get("term", ""))
        slug_counts[key] = slug_counts.get(key, 0) + 1

    collisions = {k: v for k, v in slug_counts.items() if v > 1}
    print(f"Distinct (Act, term) pairs with 2+ surviving graph nodes: {len(collisions)}")
    print("(spec's independently-verified count: 746 distinct colliding slugs, pre-rebuild)")

    print()
    print("Spot-check: ITAA 1936 'exempt income' (spec-cited 4 distinct meanings)")
    results = resolver.find_all_definitions("exempt income")
    itaa_1936 = [r for r in results if r.act_frbr_uri == "/akn/au/act/1936/27"]
    print(f"  find_all_definitions('exempt income') for ITAA 1936: {len(itaa_1936)} results")
    for r in itaa_1936:
        print(f"    - {r.definition_text[:80]}...")


if __name__ == "__main__":
    main()
