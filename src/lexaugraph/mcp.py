from __future__ import annotations
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from .graph import LexAuGraph
from .resolver import DefinitionResolver

mcp = FastMCP("lex-au-graph")
_resolver: Optional[DefinitionResolver] = None


def init(graph_path: Path) -> None:
    global _resolver
    graph = LexAuGraph.load(graph_path)
    _resolver = DefinitionResolver(graph)


def resolve_definition_tool(term: str, act_frbr_uri: str) -> str:
    if _resolver is None:
        return "Error: graph not initialised. Run `lexaugraph build` first."
    result = _resolver.resolve_definition(term, act_frbr_uri)
    if result is None:
        return f"No definition found for '{term}' in {act_frbr_uri}."
    return (
        f"**{result.display_term}** ({result.act_title} - {result.section_eid})\n\n"
        f"{result.definition_text}"
    )


def cross_references_tool(eid: str, act_frbr_uri: str) -> str:
    if _resolver is None:
        return "Error: graph not initialised. Run `lexaugraph build` first."
    refs = _resolver.cross_references(eid, act_frbr_uri)
    if not refs:
        return f"No outgoing references from {eid} in {act_frbr_uri}."
    lines = [
        f"- [{r['ref_text']}]({r['target']}) ({'cross-act' if r['is_cross_act'] else 'same-act'})"
        for r in refs
    ]
    return "\n".join(lines)


@mcp.tool()
def resolve_definition(term: str, act_frbr_uri: str) -> str:
    """Resolve a defined term to its canonical definition and section citation within an AU Act.

    Args:
        term: The term to resolve (e.g. "personal information")
        act_frbr_uri: The FRBR URI of the Act (e.g. "/akn/au/act/1988/119")
    """
    return resolve_definition_tool(term, act_frbr_uri)


@mcp.tool()
def cross_references(eid: str, act_frbr_uri: str) -> str:
    """List all outgoing cross-references from a section within an AU Act.

    Args:
        eid: The section eId (e.g. "part-I__sec-13")
        act_frbr_uri: The FRBR URI of the Act (e.g. "/akn/au/act/1988/119")
    """
    return cross_references_tool(eid, act_frbr_uri)


def find_all_definitions_tool(term: str) -> str:
    if _resolver is None:
        return "Error: graph not initialised. Run `lexaugraph build` first."
    results = _resolver.find_all_definitions(term)
    if not results:
        return f"No definitions found for '{term}'."
    parts = [
        f"**{r.display_term}** ({r.act_title} - {r.section_eid})\n\n{r.definition_text}"
        for r in results
    ]
    return "\n\n---\n\n".join(parts)


@mcp.tool()
def find_all_definitions(term: str) -> str:
    """Find all definitions of a term across all loaded Acts.

    Args:
        term: The term to search for (e.g. "personal information")
    """
    return find_all_definitions_tool(term)


def get_act_terms_tool(act_frbr_uri: str) -> str:
    if _resolver is None:
        return "Error: graph not initialised. Run `lexaugraph build` first."
    terms = _resolver.get_act_terms(act_frbr_uri)
    if not terms:
        return f"No defined terms found in {act_frbr_uri}."
    act_data = _resolver._graph.graph.nodes.get(act_frbr_uri, {})
    act_title = act_data.get("title", act_frbr_uri)
    lines = [f"{len(terms)} defined terms in {act_title} ({act_frbr_uri}):"]
    for t in terms:
        lines.append(f"- {t['display_term']} ({t['section_eid']})")
    return "\n".join(lines)


@mcp.tool()
def get_act_terms(act_frbr_uri: str) -> str:
    """List all defined terms in an AU Act.

    Args:
        act_frbr_uri: The FRBR URI of the Act (e.g. "/akn/au/act/1988/119")
    """
    return get_act_terms_tool(act_frbr_uri)
