"""Locally scoped definitions: scope parsing, default exclusion from Act-wide queries, scope-aware resolution."""
from pathlib import Path

import pytest

from lexaugraph.graph import LexAuGraph
from lexaugraph.loader import parse_act
from lexaugraph.resolver import DefinitionResolver

FIXTURES = Path(__file__).parent / "fixtures"
ENTRY = {
    "name": "Local Scope Act 2026",
    "year": 2026,
    "number": 1,
    "effective_date": "2026-01-01",
    "xml_path": "xml/local-scope-act.xml",
}
ACT = "/akn/au/act/2026/1"


@pytest.fixture()
def data():
    return parse_act(FIXTURES / "local-scope-act.xml", ENTRY)


@pytest.fixture()
def resolver(data) -> DefinitionResolver:
    g = LexAuGraph()
    g.add_act_data(data)
    return DefinitionResolver(g)


def test_loader_reads_scope_from_refers_to(data) -> None:
    scopes = {(t.term, t.scope) for t in data.defined_terms}
    assert scopes == {("use", "act"), ("use", "part-I__sec-5"), ("disclose", "part-I__sec-5")}


def test_local_terms_never_become_entities(data) -> None:
    assert all(t.entity_type is None for t in data.defined_terms if t.scope != "act")


def test_find_all_definitions_is_act_wide_by_default(resolver: DefinitionResolver) -> None:
    got = resolver.find_all_definitions("use")
    assert [r.definition_text for r in got] == ["means apply for any purpose."]
    assert resolver.find_all_definitions("disclose") == []
    assert len(resolver.find_all_definitions("use", include_local=True)) == 2


def test_aggregates_ignore_local_terms(resolver: DefinitionResolver) -> None:
    assert resolver.count_valid_defined_terms() == 1
    assert [t["term"] for t in resolver.get_act_terms(ACT)] == ["use"]
    assert len(resolver.get_act_terms(ACT, include_local=True)) == 3
    assert [d["term"] for d in resolver.get_act_definitions(ACT)] == ["use"]


def test_local_definition_wins_inside_its_scope(resolver: DefinitionResolver) -> None:
    inside = resolver.resolve_definition("use", ACT, section_eid="part-I__sec-5__subsec-1")
    assert inside is not None and "document" in inside.definition_text
    same = resolver.resolve_definition("use", ACT, section_eid="part-I__sec-5")
    assert same is not None and "document" in same.definition_text


def test_act_wide_meaning_outside_the_scope(resolver: DefinitionResolver) -> None:
    outside = resolver.resolve_definition("use", ACT, section_eid="part-I__sec-6")
    assert outside is not None and "any purpose" in outside.definition_text
    nowhere = resolver.resolve_definition("use", ACT)
    assert nowhere is not None and "any purpose" in nowhere.definition_text


def test_local_only_term_resolves_only_inside_scope(resolver: DefinitionResolver) -> None:
    assert resolver.resolve_definition("disclose", ACT, section_eid="part-I__sec-6") is None
    assert resolver.resolve_definition("disclose", ACT) is None
    inside = resolver.resolve_definition("disclose", ACT, section_eid="part-I__sec-5__subsec-1")
    assert inside is not None and "divulge" in inside.definition_text


def test_scope_survives_graph_serialisation(data, tmp_path: Path) -> None:
    g = LexAuGraph()
    g.add_act_data(data)
    path = tmp_path / "graph.json"
    g.save(path)
    loaded = LexAuGraph.load(path)
    scopes = {d.get("scope") for _, d in loaded.graph.nodes(data=True) if d.get("type") == "defined_term"}
    assert scopes == {"act", "part-I__sec-5"}
