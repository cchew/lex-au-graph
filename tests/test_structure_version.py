import json

import pytest

from lexaugraph.loader import (
    UnsupportedCorpusStructure,
    check_structure_version,
    load_corpus,
)


def _corpus(tmp_path, **extra):
    (tmp_path / "index.json").write_text(json.dumps({"acts": {}, **extra}))
    return tmp_path


@pytest.mark.parametrize("version", [1, 2])
def test_supported_versions_pass(version):
    check_structure_version({"structure_version": version})


def test_unknown_version_is_refused():
    with pytest.raises(UnsupportedCorpusStructure, match="structure_version 3"):
        check_structure_version({"structure_version": 3})


def test_missing_version_warns_but_proceeds(capsys):
    check_structure_version({"acts": {}})
    assert "no structure_version" in capsys.readouterr().err


def test_load_corpus_refuses_an_unknown_structure(tmp_path):
    with pytest.raises(UnsupportedCorpusStructure):
        load_corpus(_corpus(tmp_path, structure_version=99))


def test_load_corpus_accepts_the_current_structure(tmp_path):
    assert load_corpus(_corpus(tmp_path, structure_version=2)) == []
