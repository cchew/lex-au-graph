from __future__ import annotations
import re
from typing import Any, Optional

from . import impact
from .graph import LexAuGraph
from .models import DefinitionResult, MultiActTermSummary, _confidence_label

_JUNK_TERM_PATTERN = re.compile(
    r"^(and|or|but|the|of|in|on|at|to|for|does not|is not|means|includes?)( .*)?$",
    re.IGNORECASE,
)


def _containment_prefix(section_eid: str) -> str:
    """Return the Part/Division containment path for a section eid, e.g.
    'part-II__dvs-1__sec-6AA' -> 'part-II__dvs-1'. Returns '' for a flat
    eid with no '__'-delimited ancestry (e.g. 'sec-1'), meaning the Act
    has no Part/Division structure to scope against."""
    if "__" not in section_eid:
        return ""
    return section_eid.rsplit("__", 1)[0]


class DefinitionResolver:
    def __init__(self, graph: LexAuGraph, centrality: dict[str, float] | None = None) -> None:
        self._graph = graph
        self._centrality = centrality

    def resolve_definition(
        self, term: str, act_frbr_uri: str, section_eid: Optional[str] = None
    ) -> Optional[DefinitionResult]:
        term_lower = term.lower().strip()
        candidates: list[tuple[str, str, dict[str, Any]]] = []
        for node_id, data in self._graph.graph.nodes(data=True):
            if data.get("type") != "defined_term":
                continue
            if data.get("act_frbr_uri") != act_frbr_uri:
                continue
            if data.get("term") != term_lower:
                continue
            def_text = data.get("definition_text")
            def_section_eid = data.get("section_eid")
            if not def_text or not def_section_eid:
                continue
            candidates.append((def_section_eid, def_text, data))

        if not candidates:
            return None

        chosen = self._select_candidate(candidates, section_eid)
        if chosen is None:
            return None
        def_section_eid, def_text, data = chosen
        act_data = self._graph.graph.nodes.get(act_frbr_uri, {})
        return DefinitionResult(
            term=term,
            display_term=data.get("display_term", term),
            definition_text=def_text,
            act_frbr_uri=act_frbr_uri,
            section_eid=def_section_eid,
            act_title=act_data.get("title", act_frbr_uri),
        )

    def _select_candidate(
        self,
        candidates: list[tuple[str, str, dict[str, Any]]],
        section_eid: Optional[str],
    ) -> Optional[tuple[str, str, dict[str, Any]]]:
        if len(candidates) == 1 or section_eid is None:
            return candidates[0]

        for c in candidates:
            if c[0] == section_eid:
                return c

        query_prefix = _containment_prefix(section_eid)
        enclosing: list[tuple[int, tuple[str, str, dict[str, Any]]]] = []
        for c in candidates:
            def_prefix = _containment_prefix(c[0])
            if def_prefix and (
                query_prefix == def_prefix or query_prefix.startswith(def_prefix + "__")
            ):
                enclosing.append((len(def_prefix), c))
        if enclosing:
            enclosing.sort(key=lambda pair: -pair[0])
            return enclosing[0][1]

        # No candidate's Part/Division encloses the requesting section, and
        # there's more than one candidate (the single-candidate case
        # already returned above) -- genuine ambiguity this method won't
        # guess at. Returning None means the caller treats the term as
        # unresolved for this section rather than silently picking a
        # possibly-wrong meaning; the reader renders it as plain text.
        return None

    def cross_references(
        self, eid: str, act_frbr_uri: str
    ) -> list[dict[str, Any]]:
        section_id = f"{act_frbr_uri}#{eid}"
        results = []
        for _, target, data in self._graph.graph.out_edges(section_id, data=True):
            if data.get("type") != "ref":
                continue
            is_cross_act = data.get("is_cross_act", False)
            for citation in data.get("citations", []):
                results.append({
                    "target": target,
                    "ref_text": citation["ref_text"],
                    "is_cross_act": is_cross_act,
                    "relation": citation["relation"],
                    "relation_confidence_label": _confidence_label(citation["relation_confidence"]),
                    "extraction_confidence_label": _confidence_label(citation["extraction_confidence"]),
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

    def entities_in_section(self, eid: str, act_frbr_uri: str) -> list[dict[str, Any]]:
        """Entities (offices/agencies) mentioned in a given section, via outgoing
        mentions edges. Includes the entity's own defining section if it mentions
        itself in its definition text (mentions edges are not defines-exclusive)."""
        section_id = f"{act_frbr_uri}#{eid}"
        results = []
        for _, target, data in self._graph.graph.out_edges(section_id, data=True):
            if data.get("type") != "mentions":
                continue
            target_data = self._graph.graph.nodes.get(target, {})
            results.append({
                "node_id": target,
                "display_term": target_data.get("display_term", ""),
                "entity_type": target_data.get("entity_type"),
                "count": data.get("count", 0),
            })
        return results

    def find_entity(self, display_term: str) -> list[dict[str, Any]]:
        """Find all entity-classified defined terms across all loaded Acts matching
        display_term, exactly.

        Cross-Act canonicalization is NOT attempted: the corpus has no
        administering-department metadata, so two Acts' "Commissioner" terms
        cannot be confirmed as the same real-world office from corpus data
        alone. Results are Act-scoped homonyms, not confirmed shared identity --
        any consumer surfacing this must not imply otherwise.
        """
        results = []
        for node_id, data in self._graph.graph.nodes(data=True):
            if data.get("type") != "defined_term":
                continue
            if data.get("entity_type") is None:
                continue
            if data.get("display_term") != display_term:
                continue
            act_frbr_uri = data.get("act_frbr_uri", "")
            act_data = self._graph.graph.nodes.get(act_frbr_uri, {})
            results.append({
                "node_id": node_id,
                "display_term": data.get("display_term", ""),
                "entity_type": data.get("entity_type"),
                "act_frbr_uri": act_frbr_uri,
                "act_title": act_data.get("title", act_frbr_uri),
                "section_eid": data.get("section_eid", ""),
            })
        return results

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
