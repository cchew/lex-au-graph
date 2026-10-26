import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "restore_corpus_from_hf",
        Path(__file__).parent.parent / "scripts" / "restore_corpus_from_hf.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SHA = "ab" * 20
REMOTE = {
    "index.json": b'{"acts": {}}',
    "xml/a.xml": b"<akn>fresh</akn>",
    "reports/a.json": b"{}",  # outside allow_patterns: never downloaded or checked
}


def _entry(path, data):
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    return SimpleNamespace(path=path, size=len(data), blob_id=blob, lfs=None)


class FakeApi:
    def __init__(self, sha=SHA):
        self.sha = sha
        self.tree_calls = []

    def repo_info(self, **_):
        return SimpleNamespace(sha=self.sha)

    def list_repo_tree(self, **kwargs):
        self.tree_calls.append(kwargs)
        return [_entry(p, d) for p, d in REMOTE.items()] + [SimpleNamespace(path="xml")]


def _writer(stale=False, calls=None):
    def download(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        root = Path(kwargs["local_dir"])
        for path in ("index.json", "xml/a.xml"):
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            data = REMOTE[path]
            target.write_bytes(b"STALE" + data if stale and path.startswith("xml/") else data)
        return kwargs["local_dir"]

    return download


def test_restore_pins_revision_and_verifies(monkeypatch, tmp_path):
    module = _load_module()
    calls = []
    api = FakeApi()
    monkeypatch.setattr(module, "snapshot_download", _writer(calls=calls))
    local_dir = str(tmp_path / "corpus")

    assert module.restore("cchew/lex-au", local_dir, sleep=lambda _: None, api=api) == local_dir
    assert calls == [{
        "repo_id": "cchew/lex-au",
        "repo_type": "dataset",
        "revision": SHA,
        "local_dir": local_dir,
        "allow_patterns": ["index.json", "xml/*.xml"],
    }]
    assert api.tree_calls[0]["revision"] == SHA


def test_restore_fails_when_fallback_keeps_stale_file(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setattr(module, "snapshot_download", _writer(stale=True))
    with pytest.raises(RuntimeError, match="1 files missing or mismatched"):
        module.restore("cchew/lex-au", str(tmp_path / "corpus"), sleep=lambda _: None, api=FakeApi())


def test_restore_refetches_then_succeeds(monkeypatch, tmp_path):
    module = _load_module()
    attempts = []
    stale, good = _writer(stale=True), _writer()

    def download(**kwargs):
        attempts.append(1)
        return (stale if len(attempts) == 1 else good)(**kwargs)

    monkeypatch.setattr(module, "snapshot_download", download)
    module.restore("cchew/lex-au", str(tmp_path / "corpus"), sleep=lambda _: None, api=FakeApi())
    assert len(attempts) == 2


def test_restore_refuses_non_empty_dir(monkeypatch, tmp_path):
    module = _load_module()
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "index.json").write_text("{}")
    monkeypatch.setattr(module, "snapshot_download", _writer())
    with pytest.raises(RuntimeError, match="not empty"):
        module.restore("cchew/lex-au", str(tmp_path / "corpus"), sleep=lambda _: None, api=FakeApi())
