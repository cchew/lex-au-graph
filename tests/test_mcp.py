from pathlib import Path
import pytest
from lexaugraph.graph import LexAuGraph
from lexaugraph.loader import parse_act
from lexaugraph.resolver import DefinitionResolver
import lexaugraph.mcp as mcp_module

FIXTURES = Path(__file__).parent / "fixtures"
INDEX_ENTRY = {
    "name": "Privacy Act 1988",
    "year": 1988,
    "number": 119,
    "effective_date": "2026-06-04",
    "xml_path": "xml/privacy-act-1988.xml",
}


@pytest.fixture(autouse=True)
def setup_graph():
    act_data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    g = LexAuGraph()
    g.add_act_data(act_data)
    mcp_module._resolver = DefinitionResolver(g)
    yield
    mcp_module._resolver = None


def test_resolve_definition_tool_found():
    result = mcp_module.resolve_definition_tool("personal information", "/akn/au/act/1988/119")
    assert "part-I__sec-6" in result
    assert "identified individual" in result


def test_resolve_definition_tool_not_found():
    result = mcp_module.resolve_definition_tool("xyz unknown", "/akn/au/act/1988/119")
    assert "No definition found" in result


def test_cross_references_tool():
    result = mcp_module.cross_references_tool("part-I__sec-13", "/akn/au/act/1988/119")
    assert "section 6" in result


def test_cross_references_tool_no_refs():
    result = mcp_module.cross_references_tool("part-I__sec-1", "/akn/au/act/1988/119")
    assert isinstance(result, str)


def test_resolver_none_returns_error():
    mcp_module._resolver = None
    result = mcp_module.resolve_definition_tool("personal information", "/akn/au/act/1988/119")
    assert "not initialised" in result.lower()


def test_find_all_definitions_tool_found():
    result = mcp_module.find_all_definitions_tool("personal information")
    assert "part-I__sec-6" in result
    assert "identified individual" in result


def test_find_all_definitions_tool_not_found():
    result = mcp_module.find_all_definitions_tool("nonexistent xyz")
    assert "No definitions found" in result


def test_find_all_definitions_tool_resolver_none():
    mcp_module._resolver = None
    result = mcp_module.find_all_definitions_tool("personal information")
    assert "not initialised" in result.lower()


def test_get_act_terms_tool_returns_terms():
    result = mcp_module.get_act_terms_tool("/akn/au/act/1988/119")
    assert "personal information" in result
    assert "sensitive information" in result


def test_get_act_terms_tool_unknown_act():
    result = mcp_module.get_act_terms_tool("/akn/au/act/2009/28")
    assert "No defined terms found" in result


def test_get_act_terms_tool_resolver_none():
    mcp_module._resolver = None
    result = mcp_module.get_act_terms_tool("/akn/au/act/1988/119")
    assert "not initialised" in result.lower()
