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


@pytest.fixture()
def registrar_graph():
    index_entry = {
        "name": "Sample Registrar Act 1961", "year": 1961, "number": 12,
        "effective_date": "2026-06-04", "xml_path": "xml/registrar-entity-sample.xml",
    }
    act_data = parse_act(FIXTURES / "registrar-entity-sample.xml", index_entry)
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


def test_cross_references_tool_includes_relation_info():
    result = mcp_module.cross_references_tool("part-I__sec-13", "/akn/au/act/1988/119")
    assert "relation confidence" in result


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


def test_impact_analysis_tool_finds_direct_citer():
    result = mcp_module.impact_analysis_tool("part-I__sec-6", "/akn/au/act/1988/119")
    assert "part-I__sec-13" in result


def test_impact_analysis_tool_no_citers_returns_message():
    result = mcp_module.impact_analysis_tool("part-I__sec-13", "/akn/au/act/1988/119")
    assert "No sections cite" in result


def test_impact_analysis_tool_resolver_none_returns_error():
    mcp_module._resolver = None
    result = mcp_module.impact_analysis_tool("part-I__sec-6", "/akn/au/act/1988/119")
    assert "not initialised" in result.lower()


def test_init_loads_centrality_sidecar_when_present(tmp_path: Path):
    import json as json_module

    act_data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    g = LexAuGraph()
    g.add_act_data(act_data)
    graph_path = tmp_path / "graph.json"
    g.save(graph_path)
    (tmp_path / "centrality.json").write_text(
        json_module.dumps({"/akn/au/act/1988/119#part-I__sec-13": 0.5})
    )

    mcp_module.init(graph_path)

    result = mcp_module.impact_analysis_tool("part-I__sec-6", "/akn/au/act/1988/119")
    assert "percentile" in result


def test_init_without_centrality_sidecar_omits_percentile(tmp_path: Path):
    act_data = parse_act(FIXTURES / "privacy-act-1988.xml", INDEX_ENTRY)
    g = LexAuGraph()
    g.add_act_data(act_data)
    graph_path = tmp_path / "graph.json"
    g.save(graph_path)

    mcp_module.init(graph_path)

    result = mcp_module.impact_analysis_tool("part-I__sec-6", "/akn/au/act/1988/119")
    assert "percentile" not in result


def test_entities_tool_lists_mentions(registrar_graph):
    result = mcp_module.entities_tool("part-II__sec-10", "/akn/au/act/1961/12")
    assert "Registrar" in result
    assert "registrar" in result


def test_entities_tool_no_mentions_returns_message(registrar_graph):
    result = mcp_module.entities_tool("part-I__sec-5", "/akn/au/act/1961/12")
    assert isinstance(result, str)


def test_entities_tool_resolver_none_returns_error():
    mcp_module._resolver = None
    result = mcp_module.entities_tool("part-II__sec-10", "/akn/au/act/1961/12")
    assert "not initialised" in result.lower()


def test_find_entity_tool_found(registrar_graph):
    result = mcp_module.find_entity_tool("Registrar")
    assert "Sample Registrar Act 1961" in result
    assert "part-I__sec-5" in result


def test_find_entity_tool_not_found(registrar_graph):
    result = mcp_module.find_entity_tool("nonexistent xyz")
    assert "No entities found" in result


def test_find_entity_tool_resolver_none_returns_error():
    mcp_module._resolver = None
    result = mcp_module.find_entity_tool("Registrar")
    assert "not initialised" in result.lower()


@pytest.fixture(autouse=True)
def reset_complexity():
    yield
    mcp_module._complexity = None


def test_complexity_metrics_tool_not_initialised():
    mcp_module._complexity = None
    result = mcp_module.complexity_metrics_tool("/akn/au/act/1988/119")
    assert "not available" in result


def test_complexity_metrics_tool_unknown_act():
    mcp_module._complexity = {}
    result = mcp_module.complexity_metrics_tool("/akn/au/act/9999/1")
    assert "No complexity metrics found" in result


def test_complexity_metrics_tool_found():
    mcp_module._complexity = {
        "/akn/au/act/1988/119": {
            "title": "Privacy Act 1988",
            "pagerank_centrality": 0.005,
            "raw_citation_count": 3,
            "defined_term_count": 2,
            "defined_term_density": 0.01,
            "indeterminate_concept_count": 1,
            "indeterminate_concept_density": 0.005,
            "conditional_statement_count": 4,
            "conditional_statement_density": 0.02,
            "word_count": 200,
        }
    }
    result = mcp_module.complexity_metrics_tool("/akn/au/act/1988/119")
    assert "Privacy Act 1988" in result
    assert "3" in result  # raw_citation_count


@pytest.fixture(autouse=True)
def reset_codifiability():
    yield
    mcp_module._codifiability = None


def test_codifiability_signals_tool_not_initialised():
    mcp_module._codifiability = None
    result = mcp_module.codifiability_signals_tool("sec-1", "/akn/au/act/1988/119")
    assert "not available" in result


def test_codifiability_signals_tool_unknown_provision():
    mcp_module._codifiability = {}
    result = mcp_module.codifiability_signals_tool("sec-1", "/akn/au/act/1988/119")
    assert "No codifiability signals found" in result


def test_codifiability_signals_tool_found_with_llm_signals():
    mcp_module._codifiability = {
        "/akn/au/act/1988/119#sec-1": {
            "eid": "sec-1", "act_frbr_uri": "/akn/au/act/1988/119",
            "llm_tag": "high", "llm_reasoning": "clear obligation",
            "vagueness_tag": "low", "vagueness_reasoning": "no vague terms",
            "prescriptive_density_count": 3, "prescriptive_density_regdata_subset_count": 2,
            "prescriptive_density_tag": "medium", "agreement": "partial",
            "parse_verification_status": "not_yet_checked",
        }
    }
    result = mcp_module.codifiability_signals_tool("sec-1", "/akn/au/act/1988/119")
    assert "high" in result
    assert "clear obligation" in result
    assert "partial" in result


def test_codifiability_signals_tool_found_without_llm_signals_shows_not_computed_hint():
    mcp_module._codifiability = {
        "/akn/au/act/1988/119#sec-1": {
            "eid": "sec-1", "act_frbr_uri": "/akn/au/act/1988/119",
            "llm_tag": None, "llm_reasoning": None,
            "vagueness_tag": None, "vagueness_reasoning": None,
            "prescriptive_density_count": 1, "prescriptive_density_regdata_subset_count": 0,
            "prescriptive_density_tag": "low", "agreement": "not_computed",
            "parse_verification_status": "not_yet_checked",
        }
    }
    result = mcp_module.codifiability_signals_tool("sec-1", "/akn/au/act/1988/119")
    assert "--llm-signals" in result


def test_codifiability_act_summary_tool_not_initialised():
    mcp_module._codifiability = None
    result = mcp_module.codifiability_act_summary_tool("/akn/au/act/1988/119")
    assert "not available" in result


def test_codifiability_act_summary_tool_computes_bucket_percentages():
    mcp_module._codifiability = {
        "/akn/au/act/1988/119#sec-1": {
            "eid": "sec-1", "act_frbr_uri": "/akn/au/act/1988/119",
            "llm_tag": "high", "llm_reasoning": "x",
            "vagueness_tag": "low", "vagueness_reasoning": "x",
            "prescriptive_density_count": 3, "prescriptive_density_regdata_subset_count": 2,
            "prescriptive_density_tag": "medium", "agreement": "partial",
            "parse_verification_status": "spot_checked",
        },
        "/akn/au/act/1988/119#sec-2": {
            "eid": "sec-2", "act_frbr_uri": "/akn/au/act/1988/119",
            "llm_tag": "low", "llm_reasoning": "x",
            "vagueness_tag": "high", "vagueness_reasoning": "x",
            "prescriptive_density_count": 0, "prescriptive_density_regdata_subset_count": 0,
            "prescriptive_density_tag": "low", "agreement": "full",
            "parse_verification_status": "spot_checked",
        },
    }
    result = mcp_module.codifiability_act_summary_tool("/akn/au/act/1988/119")
    assert "2 scored provisions" in result
    assert "high: 50.0%" in result
    assert "low: 50.0%" in result
    assert "spot_checked" in result
