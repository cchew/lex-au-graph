from __future__ import annotations
from typing import Any, Optional

from .graph import LexAuGraph
from .models import DefinitionResult


class DefinitionResolver:
    def __init__(self, graph: LexAuGraph) -> None:
        self._graph = graph

    def resolve_definition(
        self, term: str, act_frbr_uri: str
    ) -> Optional[DefinitionResult]:
        term_lower = term.lower().strip()
        for node_id, data in self._graph.graph.nodes(data=True):
            if data.get("type") != "defined_term":
                continue
            if data.get("act_frbr_uri") != act_frbr_uri:
                continue
            if data.get("term") == term_lower:
                act_data = self._graph.graph.nodes.get(act_frbr_uri, {})
                return DefinitionResult(
                    term=term,
                    display_term=data.get("display_term", term),
                    definition_text=data["definition_text"],
                    act_frbr_uri=act_frbr_uri,
                    section_eid=data["section_eid"],
                    act_title=act_data.get("title", act_frbr_uri),
                )
        return None

    def cross_references(
        self, eid: str, act_frbr_uri: str
    ) -> list[dict[str, Any]]:
        section_id = f"{act_frbr_uri}#{eid}"
        results = []
        for _, target, data in self._graph.graph.out_edges(section_id, data=True):
            if data.get("type") == "ref":
                results.append({
                    "target": target,
                    "ref_text": data.get("ref_text", ""),
                    "is_cross_act": data.get("is_cross_act", False),
                })
        return results

    def find_all_definitions(self, term: str) -> list[DefinitionResult]:
        term_lower = term.lower().strip()
        results = []
        for _node_id, data in self._graph.graph.nodes(data=True):
            if data.get("type") != "defined_term":
                continue
            if data.get("term") == term_lower:
                act_frbr_uri = data.get("act_frbr_uri", "")
                act_data = self._graph.graph.nodes.get(act_frbr_uri, {})
                results.append(DefinitionResult(
                    term=term,
                    display_term=data.get("display_term", term),
                    definition_text=data["definition_text"],
                    act_frbr_uri=act_frbr_uri,
                    section_eid=data["section_eid"],
                    act_title=act_data.get("title", act_frbr_uri),
                ))
        return results

    def get_act_terms(self, act_frbr_uri: str) -> list[dict[str, str]]:
        results = []
        for _node_id, data in self._graph.graph.nodes(data=True):
            if data.get("type") != "defined_term":
                continue
            if data.get("act_frbr_uri") != act_frbr_uri:
                continue
            results.append({
                "term": data.get("term", ""),
                "display_term": data.get("display_term", ""),
                "section_eid": data.get("section_eid", ""),
            })
        return sorted(results, key=lambda r: r["term"])
