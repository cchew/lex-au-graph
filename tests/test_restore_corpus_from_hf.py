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
    "xml/big.xml": b"<akn>large lfs act</akn>",  # >10 MB XML files are LFS on HF
    "reports/a.json": b"{}",  # outside _ALLOW_PATTERNS: never downloaded or checked
}
LFS = {"xml/big.xml"}


def _blob(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _entry(path, data):
    if path in LFS:
        pointer = b"oid sha256:" + hashlib.sha256(data).hexdigest().encode()
        return SimpleNamespace(path=path, size=len(data), blob_id=_blob(pointer),
                               lfs=SimpleNamespace(sha256=hashlib.sha256(data).hexdigest()))
    return SimpleNamespace(path=path, size=len(data), blob_id=_blob(data), lfs=None)


class FakeApi:
    def __init__(self, sha=SHA):
        self.sha = sha
        self.tree_calls = []

    def repo_info(self, **_):
        return SimpleNamespace(sha=self.sha)

    def list_repo_tree(self, **kwargs):
        self.tree_calls.append(kwargs)
        return [_entry(p, d) for p, d in REMOTE.items()] + [SimpleNamespace(path="xml")]


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class RateLimited(Exception):
    def __init__(self, headers):
        super().__init__("429 Too Many Requests")
        self.response = SimpleNamespace(status_code=429, headers=headers)


def _downloader(calls=None, content=None, fail=None, on_call=None):
    counts = {}

    def download(*, repo_id, filename, repo_type, revision, local_dir):
        n = counts[filename] = counts.get(filename, 0) + 1
        if on_call is not None:
            on_call(Path(local_dir) / filename)
        if calls is not None:
            calls.append(dict(filename=filename, revision=revision, local_dir=local_dir))
        if fail is not None and (exc := fail(filename, n)) is not None:
            raise exc
        target = Path(local_dir) / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        data = content(filename, n) if content else None
        target.write_bytes(REMOTE[filename] if data is None else data)
        return str(target)

    return download


def _restore(module, local, clock=None, **kwargs):
    clock = clock or FakeClock()
    kwargs.setdefault("api", FakeApi())
    kwargs.setdefault("workers", 1)
    kwargs.setdefault("bulk", None)
    return module.restore("cchew/lex-au", str(local), sleep=clock.sleep, clock=clock, **kwargs)


def test_restore_pins_revision_and_limits_to_allow_patterns(tmp_path):
    module = _load_module()
    calls = []
    api = FakeApi()
    local_dir = tmp_path / "corpus"

    assert _restore(module, local_dir, api=api, download=_downloader(calls=calls)) == str(local_dir)
    assert sorted(c["filename"] for c in calls) == ["index.json", "xml/a.xml", "xml/big.xml"]
    assert {c["revision"] for c in calls} == {SHA}
    assert api.tree_calls[0]["revision"] == SHA


def test_restore_fails_closed_when_stale_file_persists(tmp_path):
    module = _load_module()
    stale = lambda p, n: b"STALE" + REMOTE[p] if p == "xml/a.xml" else None  # noqa: E731
    with pytest.raises(RuntimeError, match="budget spent"):
        _restore(module, tmp_path / "corpus", download=_downloader(content=stale), budget_seconds=600)


def test_restore_rejects_same_size_stale_git_blob(tmp_path):
    """Same size, so only the git blob sha1 can catch it."""
    module = _load_module()
    bad = b"<akn>stale</akn>"
    assert len(bad) == len(REMOTE["xml/a.xml"])
    stale = lambda p, n: bad if p == "xml/a.xml" else None  # noqa: E731
    with pytest.raises(RuntimeError, match="budget spent"):
        _restore(module, tmp_path / "corpus", download=_downloader(content=stale), budget_seconds=600)


def test_restore_rejects_same_size_stale_lfs_content(tmp_path):
    """LFS entry: blob_id is the pointer's sha1, so only the sha256 can tell."""
    module = _load_module()
    bad = b"<akn>stale lfs act</akn>"
    assert len(bad) == len(REMOTE["xml/big.xml"])
    stale = lambda p, n: bad if p == "xml/big.xml" else None  # noqa: E731
    with pytest.raises(RuntimeError, match="budget spent"):
        _restore(module, tmp_path / "corpus", download=_downloader(content=stale), budget_seconds=600)


def test_restore_deletes_bad_file_before_refetch(tmp_path):
    """hf_hub_download "defaults to existing file" when one is on disk, so a
    mismatch must be gone before it is asked for again."""
    module = _load_module()
    seen = []
    on_call = lambda p: seen.append(p.exists()) if p.name == "a.xml" else None  # noqa: E731
    corrupt = lambda p, n: b"bad" if (p, n) == ("xml/a.xml", 1) else None  # noqa: E731
    _restore(module, tmp_path / "corpus", download=_downloader(content=corrupt, on_call=on_call))
    assert seen == [False, False]
    assert (tmp_path / "corpus" / "xml" / "a.xml").read_bytes() == REMOTE["xml/a.xml"]


def test_restore_honours_ratelimit_header_and_resumes(tmp_path):
    module = _load_module()
    calls = []
    clock = FakeClock()
    headers = {"RateLimit": '"resolvers";r=0;t=90'}
    fail = lambda p, n: RateLimited(headers) if (p, n) == ("index.json", 1) else None  # noqa: E731
    _restore(module, tmp_path / "corpus", clock=clock, download=_downloader(calls=calls, fail=fail))
    assert clock.sleeps == [91.0]
    # 429 on the first file stops the pass; verified files are never re-requested.
    assert [c["filename"] for c in calls] == ["index.json", "index.json", "xml/a.xml", "xml/big.xml"]


def test_restore_waits_full_window_without_header_and_fails_after_budget(tmp_path):
    module = _load_module()
    clock = FakeClock()
    fail = lambda p, n: RateLimited({}) if p == "xml/a.xml" else None  # noqa: E731
    with pytest.raises(RuntimeError, match="budget spent"):
        _restore(module, tmp_path / "corpus", clock=clock, download=_downloader(fail=fail),
                 budget_seconds=1000)
    assert clock.sleeps == [300.0, 300.0, 300.0]


def test_restore_refuses_non_empty_dir(tmp_path):
    module = _load_module()
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "index.json").write_text("{}")
    calls = []
    with pytest.raises(RuntimeError, match="not empty"):
        _restore(module, tmp_path / "corpus", download=_downloader(calls=calls))
    assert calls == []


def test_bulk_checkout_is_pruned_verified_and_repaired(tmp_path):
    """A full-dataset checkout: files outside _ALLOW_PATTERNS are removed, a
    pointer left by a failed lfs pull is deleted and fetched per file."""
    module = _load_module()
    calls = []
    seen = []

    def bulk(repo, sha, target, include=None):
        assert sha == SHA and include == module._ALLOW_PATTERNS
        for path, data in {
            "index.json": REMOTE["index.json"],
            "xml/a.xml": REMOTE["xml/a.xml"],
            "xml/big.xml": b"version https://git-lfs.github.com/spec/v1\n",
            "reports/a.json": REMOTE["reports/a.json"],
            "images/a-fig-1.png": b"png",
        }.items():
            dest = Path(target) / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)

    on_call = lambda p: seen.append(p.exists())  # noqa: E731
    _restore(module, tmp_path / "corpus", bulk=bulk, download=_downloader(calls=calls, on_call=on_call))

    assert [c["filename"] for c in calls] == ["xml/big.xml"]
    assert seen == [False]
    assert not (tmp_path / "corpus" / "reports" / "a.json").exists()
    assert not (tmp_path / "corpus" / "images" / "a-fig-1.png").exists()
    assert (tmp_path / "corpus" / "xml" / "big.xml").read_bytes() == REMOTE["xml/big.xml"]


def test_bulk_failure_falls_back_to_per_file(tmp_path):
    module = _load_module()
    calls = []

    def broken(repo, sha, target, include=None):
        raise RuntimeError("git-lfs missing")

    _restore(module, tmp_path / "corpus", bulk=broken, download=_downloader(calls=calls))
    assert sorted(c["filename"] for c in calls) == ["index.json", "xml/a.xml", "xml/big.xml"]


def test_git_bulk_fetch_pins_sha_and_removes_git_dir(monkeypatch, tmp_path):
    module = _load_module()
    commands = []

    def fake_run(cmd, cwd, env, **_):
        commands.append(cmd[1:])
        assert "Bearer" not in " ".join(cmd)
        (Path(cwd) / ".git").mkdir(exist_ok=True)
        return SimpleNamespace(stdout=SHA if cmd[1] == "rev-parse" else "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setenv("HF_TOKEN", "hf_secret")
    module.git_bulk_fetch("cchew/lex-au", SHA, tmp_path / "corpus")
    assert ["fetch", "-q", "--depth", "1", "origin", SHA] in commands
    assert not (tmp_path / "corpus" / ".git").exists()


def test_git_bulk_fetch_rejects_wrong_head(monkeypatch, tmp_path):
    module = _load_module()

    def fake_run(cmd, cwd, env, **_):
        (Path(cwd) / ".git").mkdir(exist_ok=True)
        return SimpleNamespace(stdout="f" * 40 if cmd[1] == "rev-parse" else "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="not the pinned"):
        module.git_bulk_fetch("cchew/lex-au", SHA, tmp_path / "corpus")
    assert not (tmp_path / "corpus" / ".git").exists()
