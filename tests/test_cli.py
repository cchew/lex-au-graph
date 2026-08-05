from __future__ import annotations
import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from lexaugraph.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def _make_corpus(tmp_path: Path) -> Path:
    corpus_dir = tmp_path / "corpus"
    xml_dir = corpus_dir / "xml"
    xml_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "privacy-act-1988.xml", xml_dir / "privacy-act-1988.xml")
    shutil.copy(
        FIXTURES / "freedom-of-information-act-1982.xml",
        xml_dir / "freedom-of-information-act-1982.xml",
    )
    index = {
        "acts": {
            "privacy-act-1988": {
                "name": "Privacy Act 1988",
                "year": 1988,
                "number": 119,
                "effective_date": "2026-06-04",
                "xml_path": "xml/privacy-act-1988.xml",
            },
            "freedom-of-information-act-1982": {
                "name": "Freedom of Information Act 1982",
                "year": 1982,
                "number": 3,
                "effective_date": "2026-06-04",
                "xml_path": "xml/freedom-of-information-act-1982.xml",
            },
        }
    }
    (corpus_dir / "index.json").write_text(json.dumps(index))
    return corpus_dir


def test_build_writes_citation_candidates_json(tmp_path: Path):
    corpus_dir = _make_corpus(tmp_path)
    output = tmp_path / "graph.json"

    result = runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(output)])

    assert result.exit_code == 0, result.output
    candidates_path = tmp_path / "citation_candidates.json"
    assert candidates_path.exists()
    candidates = json.loads(candidates_path.read_text())
    # Both fixture Acts are loaded, so the FOI citations resolve — no unresolved candidates.
    assert candidates == []


def test_build_prints_citation_stats_breakdown(tmp_path: Path):
    corpus_dir = _make_corpus(tmp_path)
    output = tmp_path / "graph.json"

    result = runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert "Tagged citations:" in result.output
    assert "Untagged citations:" in result.output
    assert "resolved=1" in result.output


def test_centrality_writes_centrality_json(tmp_path: Path):
    corpus_dir = _make_corpus(tmp_path)
    graph_path = tmp_path / "graph.json"
    runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(graph_path)])

    result = runner.invoke(app, ["centrality", "--graph", str(graph_path)])

    assert result.exit_code == 0, result.output
    centrality_path = tmp_path / "centrality.json"
    assert centrality_path.exists()
    scores = json.loads(centrality_path.read_text())
    assert len(scores) > 0
    assert all(isinstance(v, float) for v in scores.values())


def test_impact_prints_impacted_sections(tmp_path: Path):
    corpus_dir = _make_corpus(tmp_path)
    graph_path = tmp_path / "graph.json"
    runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(graph_path)])

    result = runner.invoke(app, [
        "impact", "--eid", "part-I__sec-6", "--act", "/akn/au/act/1988/119",
        "--graph", str(graph_path),
    ])

    assert result.exit_code == 0, result.output
    assert "part-I__sec-13" in result.output


def test_impact_annotates_centrality_percentile_when_sidecar_present(tmp_path: Path):
    corpus_dir = _make_corpus(tmp_path)
    graph_path = tmp_path / "graph.json"
    runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(graph_path)])
    runner.invoke(app, ["centrality", "--graph", str(graph_path)])

    result = runner.invoke(app, [
        "impact", "--eid", "part-I__sec-6", "--act", "/akn/au/act/1988/119",
        "--graph", str(graph_path),
    ])

    assert result.exit_code == 0, result.output
    assert "percentile" in result.output


def test_build_llm_fallback_flag_constructs_client(tmp_path: Path, monkeypatch):
    corpus_dir = _make_corpus(tmp_path)
    output = tmp_path / "graph.json"
    constructed = []

    class _FakeClient:
        def __init__(self):
            constructed.append(True)

    monkeypatch.setattr("anthropic.Anthropic", _FakeClient)

    result = runner.invoke(app, [
        "build", "--corpus-dir", str(corpus_dir), "--output", str(output), "--llm-fallback",
    ])

    assert result.exit_code == 0, result.output
    assert constructed == [True]
    assert "LLM fallback enabled" in result.output


def test_build_without_llm_fallback_flag_does_not_construct_client(tmp_path: Path, monkeypatch):
    corpus_dir = _make_corpus(tmp_path)
    output = tmp_path / "graph.json"

    def _fail_if_constructed():
        raise AssertionError("anthropic.Anthropic should not be constructed without --llm-fallback")

    monkeypatch.setattr("anthropic.Anthropic", _fail_if_constructed)

    result = runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(output)])

    assert result.exit_code == 0, result.output


def _make_registrar_corpus(tmp_path: Path) -> Path:
    corpus_dir = tmp_path / "registrar_corpus"
    xml_dir = corpus_dir / "xml"
    xml_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "registrar-entity-sample.xml", xml_dir / "registrar-entity-sample.xml")
    index = {
        "acts": {
            "registrar-entity-sample": {
                "name": "Sample Registrar Act 1961",
                "year": 1961,
                "number": 12,
                "effective_date": "2026-06-04",
                "xml_path": "xml/registrar-entity-sample.xml",
            },
        }
    }
    (corpus_dir / "index.json").write_text(json.dumps(index))
    return corpus_dir


def test_entities_prints_mentioned_entities(tmp_path: Path):
    corpus_dir = _make_registrar_corpus(tmp_path)
    graph_path = tmp_path / "graph.json"
    runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(graph_path)])

    result = runner.invoke(app, [
        "entities", "--eid", "part-II__sec-10", "--act", "/akn/au/act/1961/12",
        "--graph", str(graph_path),
    ])

    assert result.exit_code == 0, result.output
    assert "Registrar" in result.output


def test_find_entity_prints_act_scoped_matches(tmp_path: Path):
    corpus_dir = _make_registrar_corpus(tmp_path)
    graph_path = tmp_path / "graph.json"
    runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(graph_path)])

    result = runner.invoke(app, [
        "find-entity", "--term", "Registrar", "--graph", str(graph_path),
    ])

    assert result.exit_code == 0, result.output
    assert "Sample Registrar Act 1961" in result.output


def test_find_entity_no_match_exits_nonzero(tmp_path: Path):
    corpus_dir = _make_registrar_corpus(tmp_path)
    graph_path = tmp_path / "graph.json"
    runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(graph_path)])

    result = runner.invoke(app, [
        "find-entity", "--term", "nonexistent xyz", "--graph", str(graph_path),
    ])

    assert result.exit_code == 1


def test_complexity_writes_complexity_json(tmp_path: Path):
    corpus_dir = _make_corpus(tmp_path)
    graph_path = tmp_path / "graph.json"
    runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(graph_path)])
    runner.invoke(app, ["centrality", "--graph", str(graph_path)])

    result = runner.invoke(app, ["complexity", "--graph", str(graph_path)])

    assert result.exit_code == 0, result.output
    complexity_path = tmp_path / "complexity.json"
    assert complexity_path.exists()
    records = json.loads(complexity_path.read_text())
    assert len(records) == 2  # privacy-act-1988 + freedom-of-information-act-1982 fixtures
    by_uri = {r["act_frbr_uri"]: r for r in records}
    assert "/akn/au/act/1988/119" in by_uri
    assert by_uri["/akn/au/act/1988/119"]["word_count"] > 0


def test_complexity_errors_without_centrality_json(tmp_path: Path):
    corpus_dir = _make_corpus(tmp_path)
    graph_path = tmp_path / "graph.json"
    runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(graph_path)])

    result = runner.invoke(app, ["complexity", "--graph", str(graph_path)])

    assert result.exit_code == 1
    assert "centrality" in result.output.lower()


def test_codifiability_without_llm_signals_writes_signal_3_only(tmp_path: Path):
    corpus_dir = _make_corpus(tmp_path)
    graph_path = tmp_path / "graph.json"
    runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(graph_path)])

    result = runner.invoke(app, ["codifiability", "--graph", str(graph_path)])

    assert result.exit_code == 0, result.output
    codifiability_path = tmp_path / "codifiability.json"
    assert codifiability_path.exists()
    records = json.loads(codifiability_path.read_text())
    assert len(records) > 0
    assert all(r["llm_tag"] is None for r in records)
    assert all(r["agreement"] == "not_computed" for r in records)


def test_codifiability_llm_signals_flag_constructs_client_and_submits_batches(tmp_path: Path, monkeypatch):
    corpus_dir = _make_corpus(tmp_path)
    graph_path = tmp_path / "graph.json"
    runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(graph_path)])

    constructed = []
    submitted_batches = []

    class _FakeBatch:
        id = "batch-fake"
        processing_status = "ended"

    class _FakeBatches:
        def create(self, requests):
            submitted_batches.append(requests)
            return _FakeBatch()
        def retrieve(self, batch_id):
            return _FakeBatch()
        def results(self, batch_id):
            return []  # no results needed to prove the flag path is exercised

    class _FakeMessages:
        batches = _FakeBatches()

    class _FakeClient:
        def __init__(self):
            constructed.append(True)
        messages = _FakeMessages()

    monkeypatch.setattr("anthropic.Anthropic", _FakeClient)

    result = runner.invoke(app, [
        "codifiability", "--graph", str(graph_path), "--llm-signals",
    ])

    assert result.exit_code == 0, result.output
    assert constructed == [True]
    assert len(submitted_batches) == 2  # signal 1 batch + signal 2 batch
    assert "real Anthropic API cost" in result.output


def test_codifiability_without_llm_signals_flag_does_not_construct_client(tmp_path: Path, monkeypatch):
    corpus_dir = _make_corpus(tmp_path)
    graph_path = tmp_path / "graph.json"
    runner.invoke(app, ["build", "--corpus-dir", str(corpus_dir), "--output", str(graph_path)])

    constructed = []
    class _FakeClient:
        def __init__(self):
            constructed.append(True)
    monkeypatch.setattr("anthropic.Anthropic", _FakeClient)

    result = runner.invoke(app, ["codifiability", "--graph", str(graph_path)])

    assert result.exit_code == 0, result.output
    assert constructed == []
