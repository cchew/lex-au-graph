"""Contract tests: the loader and graph must handle every structural shape in lex-au's golden set.

Fixtures come from the pinned `lexau-contract-fixtures` package (pyproject dev extras). A lex-au
shape change fails here before a rebuild, not after (the 2026-09 quoted-amendment incident).

Per-fixture node and edge counts are snapshotted in tests/contract_snapshot.json. When the fixture
package is bumped on purpose, regenerate with:
    python tests/test_contract_fixtures.py > tests/contract_snapshot.json
"""
import json
import os
import sys
from pathlib import Path

import pytest

try:
    import lexau_contract_fixtures as fx
except ImportError:  # pragma: no cover
    if os.environ.get("CI"):
        raise
    pytest.skip("lexau-contract-fixtures not installed", allow_module_level=True)

from lexaugraph.complexity import compute_complexity
from lexaugraph.graph import LexAuGraph
from lexaugraph.loader import SUPPORTED_STRUCTURE_VERSIONS, load_corpus

SNAPSHOT = Path(__file__).with_name("contract_snapshot.json")


def _counts(acts) -> dict:
    out = {}
    for a in acts:
        out[a.act_node.title] = {
            "sections": sum(1 for s in a.sections if s.provision_type != "quoted"),
            "quoted": sum(1 for s in a.sections if s.provision_type == "quoted"),
            "terms": len(a.defined_terms),
            "edges": len(a.ref_edges),
        }
    return dict(sorted(out.items()))


def _snapshot() -> dict:
    return {"fixtures_structure_version": fx.structure_version(), "counts": _counts(load_corpus(fx.corpus_dir()))}


@pytest.fixture(scope="module")
def acts():
    return load_corpus(fx.corpus_dir())


def test_loader_supports_the_fixture_structure_version():
    assert fx.structure_version() in SUPPORTED_STRUCTURE_VERSIONS


def test_every_fixture_act_loads(acts):
    assert len(acts) == len(fx.manifest()["fixtures"])


def test_node_ids_are_unique_within_each_act(acts):
    for a in acts:
        ids = [s.node_id for s in a.sections]
        assert len(ids) == len(set(ids)), a.act_node.title


def test_quoted_sections_are_typed_quoted_and_create_no_edges(acts):
    quoted_total = 0
    for a in acts:
        quoted = [s for s in a.sections if "__qstr-" in s.eid]
        quoted_total += len(quoted)
        assert all(s.provision_type == "quoted" for s in quoted), a.act_node.title
        ids = {s.node_id for s in quoted}
        assert not [r for r in a.ref_edges if r.source_id in ids], a.act_node.title
    assert quoted_total, "no quoted section in the golden set: quoted_amendment fixtures lost?"


def test_quoted_definitions_do_not_become_defined_terms(acts):
    slugs = fx.fixtures_with("quoted_definition")
    assert slugs
    manifest = fx.manifest()["fixtures"]
    by_slug = dict(zip(manifest, acts))  # load order == index order == manifest order
    for slug in slugs:
        quoted_defs = manifest[slug]["facts"]["quoted_definitions"]
        total_defs = manifest[slug]["facts"]["definitions"]
        # Only the Act's own (unquoted) definitions may become term nodes.
        assert len(by_slug[slug].defined_terms) <= total_defs - quoted_defs, slug


def test_quoted_text_is_excluded_from_complexity(acts):
    g = LexAuGraph()
    for a in acts:
        g.add_act_data(a)
    rows = {r.act_frbr_uri: r for r in compute_complexity(g.graph, centrality={})}
    for a in acts:
        own = " ".join(
            s.text for s in a.sections if s.provision_type != "quoted"
        )
        assert rows[a.act_node.frbr_uri].word_count == len(own.split()), a.act_node.title


def test_counts_match_the_snapshot():
    expected = json.loads(SNAPSHOT.read_text())
    assert expected["fixtures_structure_version"] == fx.structure_version()
    assert _counts(load_corpus(fx.corpus_dir())) == expected["counts"], (
        "node/edge counts moved; if the fixture package changed on purpose, regenerate the snapshot"
    )


if __name__ == "__main__":
    json.dump(_snapshot(), sys.stdout, indent=2)
    print()
