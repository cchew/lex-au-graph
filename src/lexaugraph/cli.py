from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(name="lexaugraph", help="lex-au-graph: cross-reference graph for AU legislation")

DEFAULT_GRAPH = Path("graph.json")
DEFAULT_CORPUS = Path("../../lex-au/repo/corpus")

# Sections with many candidate terms (e.g. interpretation/"Definitions" sections with 70+
# candidates) can push a single LLM response past its output token budget before finishing
# the JSON array (observed: 79 terms -> stop_reason="max_tokens", truncated/invalid JSON,
# 0 results). Batching keeps each call's output comfortably within budget.
_EXTRACTION_BATCH_SIZE = 15


@app.command()
def build(
    corpus_dir: Path = typer.Option(DEFAULT_CORPUS, "--corpus-dir", "-c", help="Path to lex-au corpus directory"),
    output: Path = typer.Option(DEFAULT_GRAPH, "--output", "-o", help="Output path for graph.json"),
    llm_fallback: bool = typer.Option(
        False, "--llm-fallback",
        help="Use an LLM to classify ambiguous ref relation types (amends/repeals/"
             "cites/references_definition). Costs real Anthropic API calls -- off by default.",
    ),
) -> None:
    """Build the cross-reference graph from the lex-au AKN corpus."""
    from .graph import LexAuGraph
    typer.echo(f"Building graph from {corpus_dir} ...")
    client = None
    if llm_fallback:
        import anthropic
        client = anthropic.Anthropic()
        typer.echo("LLM fallback enabled for ambiguous relation classification.")
    g = LexAuGraph()
    g.build(corpus_dir, client=client)
    graph_stats = g.stats()
    g.save(output)
    typer.echo(f"Graph saved to {output}")
    typer.echo(f"Nodes: {graph_stats['nodes']}  Edges: {graph_stats['edges']}")
    typer.echo(f"Node types: {graph_stats['node_types']}")
    typer.echo(f"Edge types: {graph_stats['edge_types']}")

    candidates = g.citation_candidates_report()
    candidates_path = output.parent / "citation_candidates.json"
    candidates_path.write_text(json.dumps(candidates, indent=2))
    typer.echo(f"Citation candidates written to {candidates_path} ({len(candidates)} unresolved Acts)")

    for bucket in ("tagged", "untagged"):
        s = g.citation_stats[bucket]
        typer.echo(
            f"{bucket.capitalize()} citations: total={s['total']} "
            f"self_citation_filtered={s['self_citation_filtered']} "
            f"resolved={s['resolved']} unresolved={s['unresolved']}"
        )
    combined_unresolved = g.citation_stats["tagged"]["unresolved"] + g.citation_stats["untagged"]["unresolved"]
    typer.echo(f"Combined unresolved citations (written to candidates report): {combined_unresolved}")

    sample = g.low_confidence_untagged_sample(10)
    if sample:
        typer.echo("Lowest-confidence untagged matches (for manual eyeballing):")
        for s in sample:
            typer.echo(f"  - {s}")


@app.command()
def stats(
    graph: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Path to graph.json"),
) -> None:
    """Print graph statistics."""
    from .graph import LexAuGraph
    g = LexAuGraph.load(graph)
    s = g.stats()
    typer.echo(json.dumps(s, indent=2))


@app.command()
def centrality(
    graph: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Path to graph.json"),
    output: Path = typer.Option(None, "--output", "-o", help="Output path for centrality.json (default: alongside graph.json)"),
) -> None:
    """Precompute PageRank centrality over the ref-edge subgraph and write centrality.json."""
    from .graph import LexAuGraph
    from .impact import compute_centrality
    g = LexAuGraph.load(graph)
    scores = compute_centrality(g.graph)
    out_path = output if output is not None else graph.parent / "centrality.json"
    out_path.write_text(json.dumps(scores, indent=2))
    typer.echo(f"Centrality scores for {len(scores)} nodes written to {out_path}")


@app.command()
def complexity(
    graph: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Path to graph.json"),
    output: Path = typer.Option(None, "--output", "-o", help="Output path for complexity.json (default: alongside graph.json)"),
) -> None:
    """Precompute structural complexity metrics per Act and write complexity.json."""
    import dataclasses
    from .graph import LexAuGraph
    from .complexity import compute_complexity
    g = LexAuGraph.load(graph)
    centrality_path = graph.parent / "centrality.json"
    if not centrality_path.exists():
        typer.echo(f"Error: {centrality_path} not found. Run 'lexaugraph centrality' first.", err=True)
        raise typer.Exit(1)
    centrality_scores = json.loads(centrality_path.read_text())
    results = compute_complexity(g.graph, centrality_scores)
    out_path = output if output is not None else graph.parent / "complexity.json"
    out_path.write_text(json.dumps([dataclasses.asdict(r) for r in results], indent=2))
    typer.echo(f"Complexity metrics for {len(results)} Acts written to {out_path}")


@app.command()
def resolve(
    term: str = typer.Option(..., "--term", "-t", help="Defined term to resolve"),
    act: str = typer.Option(..., "--act", "-a", help="Act FRBR URI (e.g. /akn/au/act/1988/119)"),
    section: Optional[str] = typer.Option(
        None, "--section", "-s", help="Section eId to scope resolution to (e.g. part-I__sec-6)"
    ),
    graph: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Path to graph.json"),
) -> None:
    """Resolve a defined term within an Act, optionally scoped to a section."""
    from .graph import LexAuGraph
    from .resolver import DefinitionResolver
    g = LexAuGraph.load(graph)
    resolver = DefinitionResolver(g)
    result = resolver.resolve_definition(term, act, section_eid=section)
    if result is None:
        typer.echo(f"No definition found for '{term}' in {act}" + (f" scoped to {section}." if section else "."))
        raise typer.Exit(1)
    typer.echo(f"{result.display_term} ({result.act_title} - {result.section_eid})")
    typer.echo(result.definition_text)


@app.command()
def entities(
    eid: str = typer.Option(..., "--eid", help="Section eId to list mentioned entities for"),
    act: str = typer.Option(..., "--act", "-a", help="Act FRBR URI (e.g. /akn/au/act/1988/119)"),
    graph: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Path to graph.json"),
) -> None:
    """List entities (offices/agencies) mentioned in a section."""
    from .graph import LexAuGraph
    from .resolver import DefinitionResolver
    g = LexAuGraph.load(graph)
    resolver = DefinitionResolver(g)
    results = resolver.entities_in_section(eid, act)
    if not results:
        typer.echo(f"No entities mentioned in {eid} in {act}.")
        return
    for r in results:
        typer.echo(f"{r['display_term']} ({r['entity_type']}, {r['count']} mention(s))")


@app.command(name="find-entity")
def find_entity(
    term: str = typer.Option(..., "--term", "-t", help="Exact display term to search for"),
    graph: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Path to graph.json"),
) -> None:
    """Find all Act-scoped entities matching a display term (homonym search, not identity resolution)."""
    from .graph import LexAuGraph
    from .resolver import DefinitionResolver
    g = LexAuGraph.load(graph)
    resolver = DefinitionResolver(g)
    results = resolver.find_entity(term)
    if not results:
        typer.echo(f"No entities found for '{term}'.")
        raise typer.Exit(1)
    typer.echo("Act-scoped homonym matches (not confirmed to be the same real-world office):")
    for r in results:
        typer.echo(f"- {r['display_term']} ({r['entity_type']}) in {r['act_title']} ({r['section_eid']})")


@app.command()
def extract_untagged(
    xml_path: Path = typer.Option(..., "--xml", help="Path to the Act's AKN XML file"),
    act_frbr_uri: str = typer.Option(..., "--act-frbr-uri", help="FRBR URI of the Act (must already exist in the graph)"),
    graph: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Path to graph.json"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print extracted definitions without modifying graph.json"),
) -> None:
    """Backfill untagged prose definitions for one Act into an existing graph.json, via grounded LLM extraction."""
    import anthropic
    import lxml.etree as ET
    from .graph import LexAuGraph
    from .loader import AKN, find_untagged_candidates, filter_by_recurrence, _ancestor_section_eid, _full_act_text
    from .llm_extract import chunk_section_text, extract_definitions_from_section
    from .models import DefinedTermNode

    g = LexAuGraph.load(graph)
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    full_text = _full_act_text(root)

    candidates = find_untagged_candidates(root)
    candidates = filter_by_recurrence(candidates, full_text)
    typer.echo(f"{len(candidates)} candidates survive the recurrence filter.")

    by_section: dict[str, list[tuple[str, object]]] = {}
    for term, p in candidates:
        section_eid = _ancestor_section_eid(p)
        by_section.setdefault(section_eid, []).append((term, p))

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    all_verified: list[DefinedTermNode] = []
    for section_eid, term_pairs in by_section.items():
        section_el = None
        for s in root.iter(f"{AKN}section"):
            if s.get("eId") == section_eid:
                section_el = s
                break
        if section_el is None:
            continue
        section_text = " ".join("".join(section_el.itertext()).split())
        terms_only = [t for t, _ in term_pairs]
        # Guard on input size (section_text), independent of _EXTRACTION_BATCH_SIZE which
        # only bounds output-array size (candidate-term count). A single oversized section
        # is split into token-bounded chunks; every chunk is offered the full candidate-term
        # batch rather than trying to assign each candidate to a specific chunk by character
        # offset — extract_definitions_from_section already safely omits any term whose
        # definition isn't found verbatim in the text it was given, so a chunk that doesn't
        # contain a given term's definition simply contributes nothing for that term. This
        # is the simpler, more robust option: no need to track/maintain per-candidate
        # character offsets through the itertext()/whitespace-normalisation pipeline, and no
        # risk of a mis-assigned offset silently dropping a real definition from every chunk.
        section_chunks = chunk_section_text(section_text)
        seen_terms_in_section: set[str] = set()
        for chunk in section_chunks:
            for i in range(0, len(terms_only), _EXTRACTION_BATCH_SIZE):
                batch = terms_only[i:i + _EXTRACTION_BATCH_SIZE]
                results = extract_definitions_from_section(chunk, batch, client)
                for r in results:
                    # Union across chunks: a term already verified in an earlier chunk for
                    # this section is not overwritten or duplicated by a later chunk.
                    key = r["term"].lower()
                    if key in seen_terms_in_section:
                        continue
                    seen_terms_in_section.add(key)
                    all_verified.append(DefinedTermNode(
                        term=key,
                        display_term=r["term"],
                        act_frbr_uri=act_frbr_uri,
                        section_eid=section_eid,
                        definition_text=r["definition_text"],
                    ))

    typer.echo(f"{len(all_verified)} definitions verified (byte-exact substring match).")
    for t in all_verified:
        typer.echo(f"  - {t.display_term} ({t.section_eid})")

    if dry_run:
        typer.echo("Dry run — graph.json not modified.")
        return

    backup_path = graph.with_suffix(".json.bak")
    backup_path.write_text(graph.read_text())
    typer.echo(f"Backed up existing graph to {backup_path}")

    for t in all_verified:
        g.add_defined_term(t)
    g.save(graph)
    typer.echo(f"Merged {len(all_verified)} new definitions into {graph}")


@app.command()
def impact(
    eid: str = typer.Option(..., "--eid", help="Section eId to check impact for"),
    act: str = typer.Option(..., "--act", "-a", help="Act FRBR URI (e.g. /akn/au/act/1988/119)"),
    max_hops: int = typer.Option(3, "--max-hops", help="Maximum reverse-traversal hop depth"),
    graph: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Path to graph.json"),
) -> None:
    """Show what's affected if the given section changes (reverse-reachability fan-in)."""
    from .graph import LexAuGraph
    from .resolver import DefinitionResolver
    g = LexAuGraph.load(graph)
    centrality_path = graph.parent / "centrality.json"
    centrality_scores = (
        json.loads(centrality_path.read_text()) if centrality_path.exists() else None
    )
    resolver = DefinitionResolver(g, centrality=centrality_scores)
    results = resolver.impacted_by(eid, act, max_hops=max_hops)
    if not results:
        typer.echo(f"No sections cite {eid} in {act} within {max_hops} hops.")
        return
    results.sort(key=lambda r: -r["path_weight"])
    for r in results:
        pct = r.get("centrality_percentile")
        pct_str = f", centrality: {pct}th percentile" if pct is not None else ""
        typer.echo(f"{r['node_id']} (hop {r['hop']}, weight {r['path_weight']:.2f}{pct_str})")
        for t in r["ref_texts"]:
            typer.echo(f"    cites via '{t}'")


@app.command()
def serve(
    graph: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Path to graph.json"),
) -> None:
    """Start the FastMCP server (stdio transport)."""
    from . import mcp as mcp_module
    try:
        mcp_module.init(graph)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    mcp_module.mcp.run()
