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
def serve(
    graph: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Path to graph.json"),
) -> None:
    """Start the FastMCP server (stdio transport)."""
    from . import mcp as mcp_module
    mcp_module.init(graph)
    mcp_module.mcp.run()
