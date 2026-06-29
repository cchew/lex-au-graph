from __future__ import annotations
import json
from pathlib import Path
from typing import Any

import networkx as nx

from .loader import load_corpus
from .models import ActData, RefEdge


class LexAuGraph:
    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()
        self._title_index: dict[str, str] = {}

    def build(self, corpus_dir: Path) -> None:
        acts: list[ActData] = list(load_corpus(corpus_dir))
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
        )
        if act.title:
            self._title_index[act.title.lower()] = act.frbr_uri

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
            self.graph.add_edge(act.frbr_uri, section.node_id, type="contains")

        for term in act_data.defined_terms:
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
                self.graph.add_edge(section_id, term.node_id, type="defines")

    def _resolve_refs(self, act_data: ActData) -> None:
        act = act_data.act_node
        for ref in act_data.ref_edges:
            target_id = self._resolve_ref(ref, act.frbr_uri)
            if target_id and target_id in self.graph.nodes:
                self.graph.add_edge(
                    ref.source_id,
                    target_id,
                    type="ref",
                    ref_text=ref.ref_text,
                    is_cross_act=ref.is_cross_act,
                )

    def _resolve_ref(self, ref: RefEdge, act_frbr_uri: str) -> str | None:
        href = ref.target_href
        if href.startswith("#"):
            return f"{act_frbr_uri}{href}"
        if href.startswith("/akn/au"):
            return href
        # Unresolved cross-act ref: try to match ref_text against known act titles
        return self._title_index.get(ref.ref_text.lower().strip())

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
        data = json.loads(path.read_text())
        g = cls()
        g.graph = nx.node_link_graph(data, edges="edges")
        return g
