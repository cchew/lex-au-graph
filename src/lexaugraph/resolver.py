from __future__ import annotations
import re
from typing import Any, Optional

from . import impact
from .graph import LexAuGraph
from .models import DefinitionResult, MultiActTermSummary

_JUNK_TERM_PATTERN = re.compile(
    r"^(and|or|but|the|of|in|on|at|to|for|does not|is not|means|includes?)( .*)?$",
    re.IGNORECASE,
)


class DefinitionResolver:
    def __init__(self, graph: LexAuGraph, centrality: dict[str, float] | None = None) -> None:
        self._graph = graph
        self._centrality = centrality

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
                def_text = data.get("definition_text")
                section_eid = data.get("section_eid")
                if not def_text or not section_eid:
                    continue
                act_data = self._graph.graph.nodes.get(act_frbr_uri, {})
                return DefinitionResult(
                    term=term,
                    display_term=data.get("display_term", term),
                    definition_text=def_text,
                    act_frbr_uri=act_frbr_uri,
                    section_eid=section_eid,
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
                citations = data.get("citations", [])
                ref_text = citations[0]["ref_text"] if citations else ""
                results.append({
                    "target": target,
                    "ref_text": ref_text,
                    "is_cross_act": data.get("is_cross_act", False),
                })
        return results

    def impacted_by(
        self, eid: str, act_frbr_uri: str, max_hops: int = 3
    ) -> list[dict[str, Any]]:
        section_id = f"{act_frbr_uri}#{eid}"
        nodes = impact.impacted_by(self._graph.graph, section_id, max_hops=max_hops)
        results = []
        for n in nodes:
            entry: dict[str, Any] = {
                "node_id": n.node_id,
                "hop": n.hop,
                "path_weight": n.path_weight,
                "ref_texts": n.ref_texts,
            }
            if self._centrality is not None:
                entry["centrality_percentile"] = impact.centrality_percentile(
                    self._centrality, n.node_id
                )
            results.append(entry)
        return results

    def find_all_definitions(self, term: str) -> list[DefinitionResult]:
        term_lower = term.lower().strip()
        results = []
        for _node_id, data in self._graph.graph.nodes(data=True):
            if data.get("type") != "defined_term":
                continue
            if data.get("term") == term_lower:
                def_text = data.get("definition_text")
                section_eid = data.get("section_eid")
                if not def_text or not section_eid:
                    continue
                act_frbr_uri = data.get("act_frbr_uri", "")
                act_data = self._graph.graph.nodes.get(act_frbr_uri, {})
                results.append(DefinitionResult(
                    term=term,
                    display_term=data.get("display_term", term),
                    definition_text=def_text,
                    act_frbr_uri=act_frbr_uri,
                    section_eid=section_eid,
                    act_title=act_data.get("title", act_frbr_uri),
                ))
        return results

    def get_act_title(self, act_frbr_uri: str) -> str:
        data = self._graph.graph.nodes.get(act_frbr_uri, {})
        return data.get("title", act_frbr_uri)

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

    def list_multi_act_terms(self, min_acts: int = 3) -> list[MultiActTermSummary]:
        """Group defined_term nodes by term across all Acts, for the browse-list UI.

        Applies a display-only junk-filter heuristic (stopword/fragment pattern, or
        shorter than 4 chars) to drop obvious extraction fragments like "and" or "does
        not". This does not fix the underlying extraction — real extraction-quality
        fixes belong in lex-au, alongside the "Term/def structured-list gap" style
        entries in lex-au/FUTURE.md, if the noise turns out to matter beyond this UI.
        """
        groups: dict[str, dict[str, Any]] = {}
        for _node_id, data in self._graph.graph.nodes(data=True):
            if data.get("type") != "defined_term":
                continue
            def_text = data.get("definition_text")
            section_eid = data.get("section_eid")
            if not def_text or not section_eid:
                continue
            term = data.get("term", "")
            entry = groups.setdefault(
                term, {"display_term": data.get("display_term", term), "acts": set()}
            )
            entry["acts"].add(data.get("act_frbr_uri", ""))

        summaries = []
        for term, info in groups.items():
            act_count = len(info["acts"])
            if act_count < min_acts:
                continue
            if len(term) < 4 or _JUNK_TERM_PATTERN.match(term):
                continue
            summaries.append(
                MultiActTermSummary(
                    term=term, display_term=info["display_term"], act_count=act_count
                )
            )
        return sorted(summaries, key=lambda s: -s.act_count)

    def count_acts(self) -> int:
        return sum(
            1 for _node_id, data in self._graph.graph.nodes(data=True)
            if data.get("type") == "act"
        )

    def count_valid_defined_terms(self) -> int:
        count = 0
        for _node_id, data in self._graph.graph.nodes(data=True):
            if data.get("type") != "defined_term":
                continue
            if data.get("definition_text") and data.get("section_eid"):
                count += 1
        return count
