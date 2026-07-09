from __future__ import annotations
import json
from pathlib import Path

import typer

app = typer.Typer(name="lexaugraph", help="lex-au-graph: cross-reference graph for AU legislation")

DEFAULT_GRAPH = Path("graph.json")
DEFAULT_CORPUS = Path("../../lex-au/repo/corpus")


@app.command()
def build(
    corpus_dir: Path = typer.Option(DEFAULT_CORPUS, "--corpus-dir", "-c", help="Path to lex-au corpus directory"),
    output: Path = typer.Option(DEFAULT_GRAPH, "--output", "-o", help="Output path for graph.json"),
) -> None:
    """Build the cross-reference graph from the lex-au AKN corpus."""
    from .graph import LexAuGraph
    typer.echo(f"Building graph from {corpus_dir} ...")
    g = LexAuGraph()
    g.build(corpus_dir)
    graph_stats = g.stats()
    g.save(output)
    typer.echo(f"Graph saved to {output}")
    typer.echo(f"Nodes: {graph_stats['nodes']}  Edges: {graph_stats['edges']}")
    typer.echo(f"Node types: {graph_stats['node_types']}")
    typer.echo(f"Edge types: {graph_stats['edge_types']}")


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
def resolve(
    term: str = typer.Option(..., "--term", "-t", help="Defined term to resolve"),
    act: str = typer.Option(..., "--act", "-a", help="Act FRBR URI (e.g. /akn/au/act/1988/119)"),
    graph: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Path to graph.json"),
) -> None:
    """Resolve a defined term within an Act."""
    from .graph import LexAuGraph
    from .resolver import DefinitionResolver
    g = LexAuGraph.load(graph)
    resolver = DefinitionResolver(g)
    result = resolver.resolve_definition(term, act)
    if result is None:
        typer.echo(f"No definition found for '{term}' in {act}.")
        raise typer.Exit(1)
    typer.echo(f"{result.display_term} ({result.act_title} - {result.section_eid})")
    typer.echo(result.definition_text)


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
    from .llm_extract import extract_definitions_from_section
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
        results = extract_definitions_from_section(section_text, terms_only, client)
        for r in results:
            all_verified.append(DefinedTermNode(
                term=r["term"].lower(),
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
