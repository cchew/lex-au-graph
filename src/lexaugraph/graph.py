from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

import anthropic
import networkx as nx

from .citations import is_self_citation, normalize_title
from .loader import load_corpus
from .models import ActData, DefinedTermNode, RefEdge


def _section_number_from_eid(eid: str) -> str | None:
    """Extract the trailing section number from a SectionNode.eid, e.g.
    'part-II__dvs-1__sec-6AA' -> '6AA'. Returns None for eids with no
    trailing 'sec-' segment (e.g. schedule provisions)."""
    last_segment = eid.rsplit("__", 1)[-1]
    if last_segment.startswith("sec-"):
        return last_segment[len("sec-"):]
    return None


def _build_entity_mention_pattern(entity_terms: list[DefinedTermNode]) -> re.Pattern | None:
    """Build one combined, non-overlapping, hyphen-aware regex matching any of
    the given entity terms' display_term values.

    Terms are sorted longest-first so a qualified variant ("the Registrar") is
    matched whole, not double-counted via its shorter substring ("Registrar")
    when both are separately defined DefinedTermNodes in the same Act.
    Hyphens count as word-continuation characters (via lookaround instead of
    \\b) so "Registrar-General" never matches bare "Registrar".
    """
    if not entity_terms:
        return None
    ordered = sorted(entity_terms, key=lambda t: -len(t.display_term))
    alternation = "|".join(re.escape(t.display_term) for t in ordered)
    return re.compile(rf"(?<![\w-])(?:{alternation})(?![\w-])")


class LexAuGraph:
    def __init__(self) -> None:
        self.graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._title_index: dict[str, str] = {}
        self._section_number_index: dict[str, dict[str, str]] = {}
        self._citation_candidates: dict[str, dict[str, Any]] = {}
        self._untagged_matches: list[str] = []
        # Refs that failed to resolve because the target Act hadn't been loaded yet.
        # Retried whenever a new Act's title lands in _title_index, since acts can be
        # added to the graph in any order via repeated add_act_data() calls.
        # (title, ref, source_act_frbr_uri, bucket)
        self._pending_refs: list[tuple[str, RefEdge, str, str]] = []
        self.citation_stats: dict[str, dict[str, int]] = {
            "tagged": {"total": 0, "self_citation_filtered": 0, "resolved": 0, "unresolved": 0},
            "untagged": {"total": 0, "self_citation_filtered": 0, "resolved": 0, "unresolved": 0},
        }

    def build(self, corpus_dir: Path, client: "anthropic.Anthropic | None" = None) -> None:
        acts: list[ActData] = list(load_corpus(corpus_dir, client=client))
        for act_data in acts:
            self._add_act_nodes(act_data)
        for act_data in acts:
            self._resolve_refs(act_data)

    def add_act_data(self, act_data: ActData) -> None:
        self._add_act_nodes(act_data)
        self._resolve_refs(act_data)

    def _add_act_nodes(self, act_data: ActData) -> None:
        act = act_data.act_node
        self.graph.add_node(
            act.frbr_uri,
            type="act",
            title=act.title,
            year=act.year,
            compilation_date=act.compilation_date,
            title_id=act.title_id,
        )
        if act.title:
            self._title_index[act.title.lower()] = act.frbr_uri
            normalized_own_title = normalize_title(act.title)
            if normalized_own_title is not None:
                self._retry_pending_refs(normalized_own_title[0], act.frbr_uri)

        for section in act_data.sections:
            self.graph.add_node(
                section.node_id,
                type="section",
                eid=section.eid,
                act_frbr_uri=section.act_frbr_uri,
                heading=section.heading,
                text=section.text,
                provision_type=section.provision_type,
            )
            self.graph.add_edge(act.frbr_uri, section.node_id, key="contains", type="contains")
            section_number = _section_number_from_eid(section.eid)
            if section_number:
                self._section_number_index.setdefault(section.act_frbr_uri, {})[section_number] = section.node_id

        term_occurrence_counts: dict[str, int] = {}
        for term in act_data.defined_terms:
            slug = term.term.replace(" ", "_").replace("-", "_")
            term_occurrence_counts[slug] = term_occurrence_counts.get(slug, 0) + 1
            term.occurrence = term_occurrence_counts[slug]
            self.graph.add_node(
                term.node_id,
                type="defined_term",
                term=term.term,
                display_term=term.display_term,
                act_frbr_uri=term.act_frbr_uri,
                section_eid=term.section_eid,
                definition_text=term.definition_text,
                entity_type=term.entity_type,
            )
            if term.section_eid:
                section_id = f"{term.act_frbr_uri}#{term.section_eid}"
                if section_id in self.graph.nodes:
                    self.graph.add_edge(section_id, term.node_id, key="defines", type="defines")

        self._add_entity_mentions(act_data)

    def _add_entity_mentions(self, act_data: ActData) -> None:
        entity_terms = [t for t in act_data.defined_terms if t.entity_type]
        pattern = _build_entity_mention_pattern(entity_terms)
        if pattern is None:
            return
        by_display_term = {t.display_term: t for t in entity_terms}
        for section in act_data.sections:
            counts: dict[str, int] = {}
            for match in pattern.finditer(section.text):
                counts[match.group(0)] = counts.get(match.group(0), 0) + 1
            for display_term, count in counts.items():
                term = by_display_term[display_term]
                self.graph.add_edge(
                    section.node_id, term.node_id,
                    key="mentions", type="mentions", count=count,
                )

    def add_defined_term(self, term: DefinedTermNode) -> None:
        """Add a single verified defined term without re-adding act/section nodes.

        Used to backfill untagged prose definitions recovered by the LLM extraction
        pipeline into a graph.json where the Act and its sections already exist.
        """
        self.graph.add_node(
            term.node_id,
            type="defined_term",
            term=term.term,
            display_term=term.display_term,
            act_frbr_uri=term.act_frbr_uri,
            section_eid=term.section_eid,
            definition_text=term.definition_text,
        )
        section_id = f"{term.act_frbr_uri}#{term.section_eid}"
        if section_id in self.graph.nodes:
            self.graph.add_edge(section_id, term.node_id, key="defines", type="defines")

    def _resolve_refs(self, act_data: ActData) -> None:
        act = act_data.act_node
        for ref in act_data.ref_edges:
            target_id = self._resolve_ref(ref, act.frbr_uri, act.title)
            if target_id and target_id in self.graph.nodes:
                self._add_or_increment_ref_edge(ref.source_id, target_id, ref)

    def _add_or_increment_ref_edge(self, source_id: str, target_id: str, ref: RefEdge) -> None:
        citation = {
            "ref_text": ref.ref_text,
            "relation": ref.relation.value,
            "relation_confidence": ref.relation_confidence,
            "extraction_confidence": ref.extraction_confidence,
        }
        if self.graph.has_edge(source_id, target_id, key="ref"):
            edge = self.graph.edges[source_id, target_id, "ref"]
            edge["citations"].append(citation)
            edge["weight"] = len(edge["citations"])
            edge["ref_texts"] = [c["ref_text"] for c in edge["citations"]]
        else:
            self.graph.add_edge(
                source_id,
                target_id,
                key="ref",
                type="ref",
                is_cross_act=ref.is_cross_act,
                citations=[citation],
                weight=1,
                ref_texts=[ref.ref_text],
            )

    def _resolve_ref(self, ref: RefEdge, act_frbr_uri: str, act_title: str) -> str | None:
        href = ref.target_href
        if href and href.startswith("#"):
            return f"{act_frbr_uri}{href}"
        if href and href.startswith("/akn/au"):
            return href
        if not ref.is_cross_act:
            if ref.matched_section:
                act_index = self._section_number_index.get(act_frbr_uri, {})
                return act_index.get(ref.matched_section)
            return None

        bucket = "untagged" if ref.matched_title else "tagged"
        if bucket == "untagged":
            self._untagged_matches.append(ref.matched_title)

        raw = ref.matched_title if ref.matched_title else ref.ref_text
        normalized = normalize_title(raw)
        if normalized is None:
            return None
        title, year = normalized

        if is_self_citation(title, act_title):
            self.citation_stats[bucket]["self_citation_filtered"] += 1
            return None

        self.citation_stats[bucket]["total"] += 1
        target_id = self._title_index.get(title)
        if target_id is None:
            self.citation_stats[bucket]["unresolved"] += 1
            self._record_unresolved(title, year, act_frbr_uri)
            self._pending_refs.append((title, ref, act_frbr_uri, bucket))
        else:
            self.citation_stats[bucket]["resolved"] += 1
        return target_id

    def _record_unresolved(self, title: str, year: int, source_act_frbr_uri: str) -> None:
        entry = self._citation_candidates.setdefault(
            title, {"title": title, "year": year, "mention_count": 0, "cited_by": {}}
        )
        entry["mention_count"] += 1
        entry["cited_by"][source_act_frbr_uri] = entry["cited_by"].get(source_act_frbr_uri, 0) + 1

    def _retry_pending_refs(self, newly_indexed_title: str, target_frbr_uri: str) -> None:
        """Retroactively resolve refs recorded as unresolved before their target Act loaded.

        Acts can be added to the graph in any order via repeated add_act_data() calls, so a
        citation to an Act that hasn't loaded yet must not be permanently lost once that Act
        does load. Matching entries are turned into graph edges and removed from both the
        pending queue and the candidates/stats bookkeeping that treated them as unresolved.
        """
        still_pending: list[tuple[str, RefEdge, str, str]] = []
        for title, ref, source_act_frbr_uri, bucket in self._pending_refs:
            if title != newly_indexed_title:
                still_pending.append((title, ref, source_act_frbr_uri, bucket))
                continue
            if target_frbr_uri in self.graph.nodes:
                self._add_or_increment_ref_edge(ref.source_id, target_frbr_uri, ref)
            self.citation_stats[bucket]["unresolved"] -= 1
            self.citation_stats[bucket]["resolved"] += 1
            self._unrecord_unresolved(title, source_act_frbr_uri)
        self._pending_refs = still_pending

    def _unrecord_unresolved(self, title: str, source_act_frbr_uri: str) -> None:
        entry = self._citation_candidates.get(title)
        if entry is None:
            return
        entry["mention_count"] -= 1
        entry["cited_by"][source_act_frbr_uri] -= 1
        if entry["cited_by"][source_act_frbr_uri] <= 0:
            del entry["cited_by"][source_act_frbr_uri]
        if entry["mention_count"] <= 0:
            del self._citation_candidates[title]

    def citation_candidates_report(self) -> list[dict[str, Any]]:
        return sorted(self._citation_candidates.values(), key=lambda e: -e["mention_count"])

    def low_confidence_untagged_sample(self, n: int = 10) -> list[str]:
        return sorted(self._untagged_matches, key=lambda t: len(t.split()))[:n]

    def stats(self) -> dict[str, Any]:
        node_types: dict[str, int] = {}
        for _, data in self.graph.nodes(data=True):
            t = data.get("type", "unknown")
            node_types[t] = node_types.get(t, 0) + 1

        edge_types: dict[str, int] = {}
        for _, _, data in self.graph.edges(data=True):
            t = data.get("type", "unknown")
            edge_types[t] = edge_types.get(t, 0) + 1

        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "node_types": node_types,
            "edge_types": edge_types,
        }

    def get_sections(self, act_frbr_uri: str) -> list[dict[str, Any]]:
        return [
            data
            for _, data in self.graph.nodes(data=True)
            if data.get("type") == "section" and data.get("act_frbr_uri") == act_frbr_uri
        ]

    def save(self, path: Path) -> None:
        data = nx.node_link_data(self.graph, edges="edges")
        path.write_text(json.dumps(data, default=str))

    @classmethod
    def load(cls, path: Path) -> LexAuGraph:
        if not path.exists():
            raise FileNotFoundError(
                f"Graph file not found: {path}. Run 'lexaugraph build' first."
            )
        data = json.loads(path.read_text())
        if not data.get("multigraph"):
            raise ValueError(
                f"{path} was built with an older single-edge-per-pair graph format "
                "(pre-MultiDiGraph migration). Rebuild it with 'lexaugraph build' "
                "before loading with this version of lexaugraph."
            )
        g = cls()
        g.graph = nx.node_link_graph(data, edges="edges")
        return g
