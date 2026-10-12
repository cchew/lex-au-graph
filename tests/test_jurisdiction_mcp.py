"""Jurisdiction labels and scope options on the MCP tools."""
from pathlib import Path

import pytest

from lexaugraph import mcp as mcp_mod
from lexaugraph.graph import LexAuGraph
from lexaugraph.loader import parse_act
from lexaugraph.models import jurisdiction_of
from lexaugraph.resolver import DefinitionResolver

FIXTURES = Path(__file__).parent / "fixtures"
ENTRY = {"name": "Local Scope Act 2026", "year": 2026, "number": 1, "effective_date": "2026-01-01", "xml_path": "x"}
ACT = "/akn/au/act/2026/1"


@pytest.mark.parametrize(
    "uri,label",
    [
        ("/akn/au/act/1988/119", "Cth"),
        ("/akn/au-vic/act/2014/60", "Vic"),
        ("/akn/au-nsw/act/1998/133", "NSW"),
        ("/akn/au-act/act/2014/24", "ACT"),
        ("/akn/au-xx/act/2014/24", "XX"),
        ("not-a-uri", "Cth"),
    ],
)
def test_jurisdiction_of(uri: str, label: str) -> None:
    assert jurisdiction_of(uri) == label


@pytest.fixture()
def tools(monkeypatch):
    g = LexAuGraph()
    g.add_act_data(parse_act(FIXTURES / "local-scope-act.xml", ENTRY))
    monkeypatch.setattr(mcp_mod, "_resolver", DefinitionResolver(g))
    return mcp_mod


def test_resolve_definition_tool_reaches_local_definitions_with_section_eid(tools) -> None:
    assert "No definition found" in tools.resolve_definition_tool("disclose", ACT)
    inside = tools.resolve_definition_tool("disclose", ACT, "part-I__sec-5__subsec-1")
    assert "divulge or communicate" in inside


def test_find_all_definitions_tool_local_option(tools) -> None:
    assert "No definitions found" in tools.find_all_definitions_tool("disclose")
    assert "divulge" in tools.find_all_definitions_tool("disclose", include_local=True)


def test_find_all_definitions_tool_jurisdiction_filter(tools) -> None:
    assert "No definitions found" in tools.find_all_definitions_tool("use", jurisdiction="Vic")
    assert "any purpose" in tools.find_all_definitions_tool("use", jurisdiction="cth")


def test_non_cth_results_carry_the_jurisdiction(tools) -> None:
    from lexaugraph.models import DefinitionResult

    r = DefinitionResult("t", "t", "x", "/akn/au-vic/act/2014/60", "sec-1", "Privacy and Data Protection Act 2014")
    assert r.act_label == "Privacy and Data Protection Act 2014 (Vic)"
    c = DefinitionResult("t", "t", "x", "/akn/au/act/1988/119", "sec-1", "Privacy Act 1988")
    assert c.act_label == "Privacy Act 1988"


def test_get_act_terms_tool_local_option(tools) -> None:
    assert "1 defined terms" in tools.get_act_terms_tool(ACT)
    assert "3 defined terms" in tools.get_act_terms_tool(ACT, include_local=True)


def test_definition_results_carry_scope(tools) -> None:
    from lexaugraph.resolver import DefinitionResolver

    r = mcp_mod._resolver
    assert isinstance(r, DefinitionResolver)
    scopes = {d.scope for d in r.find_all_definitions("use", include_local=True)}
    assert scopes == {"act", "part-I__sec-5"}
