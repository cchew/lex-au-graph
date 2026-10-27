"""Restore the published lex-au corpus from Hugging Face into a local
directory, so this repo's build pipeline has something to build against
in a fresh CI checkout (corpus/ is not checked into this repo).

This repo only reads the corpus; it never exports back to cchew/lex-au,
so there is no sync stamp to write.

_ALLOW_PATTERNS restricts the download to what lexaugraph build actually
reads (index.json + xml/*.xml, ~3,090 files). Found necessary the hard way
(2026-09-29): cchew/lex-au publishes 11,387 files total, and an unfiltered
snapshot_download from a GitHub Actions runner hit HF's 429 rate limit and
the workflow's 30-minute timeout.

Pinned and verified (2026-10-26, after lex-au's 2026-10-25 clobber): under
429s snapshot_download can log "Defaulting to existing file" and keep
whatever is already on disk. So the target must be empty, the head sha is
resolved once and every file comes from that revision, and each file is
checked against the revision's tree (LFS sha256 or git blob sha1).
Mismatches are deleted and re-fetched.

Bulk path (2026-10-27): a shallow git fetch of the pinned sha plus a
batched `git lfs pull` replaces ~3,090 per-file requests; whatever fails
verification afterwards (or everything, if git is unavailable) goes to the
per-file loop. --no-git skips it.

Rate limits (2026-10-27, mirrors lex-au's scripts/restore_corpus_from_hf.py):
each file costs one HF "resolvers" request, and lex-au's own restore shares
the same token's window. The restore works in passes: each fetches only
files not yet verified, stops early on a 429, waits for the window to reset
(RateLimit / Retry-After header, else 300 s) and resumes, until a
wall-clock budget (default 60 min, --budget-minutes or
LEXAU_RESTORE_BUDGET_MINUTES) is spent. Only then does it exit non-zero.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import filter_repo_objects

try:  # huggingface_hub >= 1.x
    from huggingface_hub.utils import parse_ratelimit_headers
except ImportError:  # pragma: no cover - older hub: fall back to Retry-After / window
    def parse_ratelimit_headers(_headers):
        return None

_ALLOW_PATTERNS = ["index.json", "xml/*.xml"]
MAX_WORKERS = 4
DEFAULT_BUDGET_MINUTES = 60.0
RATE_LIMIT_WINDOW_SECONDS = 300
ERROR_BACKOFF_SECONDS = 30
_CHUNK = 1 << 20


def _digest(path: Path, algo: str, prefix: bytes = b"") -> str:
    h = hashlib.new(algo)
    h.update(prefix)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _matches(path: Path, entry) -> bool:
    size = path.stat().st_size
    if size != entry.size:
        return False
    lfs = getattr(entry, "lfs", None)
    if lfs:
        return _digest(path, "sha256") == lfs.sha256
    return _digest(path, "sha1", f"blob {size}\0".encode()) == entry.blob_id


def _remote_files(api, repo: str, sha: str) -> dict:
    entries = {
        e.path: e
        for e in api.list_repo_tree(repo_id=repo, repo_type="dataset", revision=sha, recursive=True)
        if getattr(e, "blob_id", None) is not None
    }
    keep = set(filter_repo_objects(list(entries), allow_patterns=_ALLOW_PATTERNS))
    return {p: e for p, e in entries.items() if p in keep}


def _problems(root: Path, remote: dict) -> list[tuple[str, str]]:
    out = []
    for path, entry in sorted(remote.items()):
        local = root / path
        if not local.is_file():
            out.append((path, "missing"))
        elif not _matches(local, entry):
            out.append((path, "content differs"))
    return out


def rate_limit_wait(exc: BaseException) -> float | None:
    """Seconds to wait if exc (or anything it wraps) is an HF 429, else None."""
    seen = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        response = getattr(cur, "response", None)
        if response is not None and getattr(response, "status_code", None) == 429:
            headers = getattr(response, "headers", None) or {}
            info = parse_ratelimit_headers(headers)
            if info is not None:
                return float(info.reset_in_seconds) + 1
            for key in headers:
                if key.lower() == "retry-after":
                    try:
                        return float(headers[key]) + 1
                    except (TypeError, ValueError):
                        break
            return float(RATE_LIMIT_WINDOW_SECONDS)
        text = str(cur)
        if response is None and ("429" in text or "rate limit" in text.lower()):
            return float(RATE_LIMIT_WINDOW_SECONDS)
        cur = cur.__cause__ or cur.__context__
    return None


def git_bulk_fetch(repo: str, sha: str, target: Path, include: list[str] | None = None) -> None:
    """One shallow git fetch of the pinned sha plus a batched `git lfs pull`,
    then drop .git (mirrors lex-au's scripts/restore_corpus_from_hf.py).
    Measured 2026-10-27 on the full lex-au dataset: 221 s, no 429s, vs
    2,754 s per file. Its output is verified like any other download."""
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1", GIT_TERMINAL_PROMPT="0")
    token = os.environ.get("HF_TOKEN")
    if token:
        # Through the environment so it is never written to .git/config.
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.extraHeader",
                   GIT_CONFIG_VALUE_0=f"Authorization: Bearer {token}")

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=target, env=env, check=True,
                              capture_output=True, text=True).stdout.strip()

    target.mkdir(parents=True, exist_ok=True)
    try:
        git("init", "-q", ".")
        git("remote", "add", "origin", f"{endpoint}/datasets/{repo}")
        git("fetch", "-q", "--depth", "1", "origin", sha)
        git("checkout", "-q", "FETCH_HEAD")
        head = git("rev-parse", "HEAD")
        if head != sha:
            raise RuntimeError(f"git checked out {head}, not the pinned {sha}")
        lfs = ["lfs", "pull"]
        if include:
            lfs += ["--include", ",".join(include)]
        git(*lfs)
    finally:
        shutil.rmtree(target / ".git", ignore_errors=True)


def _fetch_pass(repo, sha, target, paths, remote, download, workers):
    stop = threading.Event()
    lock = threading.Lock()
    verified: list[str] = []
    failed: list[str] = []
    waits: list[float] = []
    errors: list[str] = []

    def one(path: str) -> None:
        if stop.is_set():
            return
        try:
            download(repo_id=repo, filename=path, repo_type="dataset",
                     revision=sha, local_dir=str(target))
        except Exception as exc:  # noqa: BLE001 - classified below
            wait = rate_limit_wait(exc)
            with lock:
                if wait is not None:
                    waits.append(wait)
                    stop.set()
                else:
                    errors.append(f"{path}: {exc}")
            (target / path).unlink(missing_ok=True)
            return
        local = target / path
        ok = local.is_file() and _matches(local, remote[path])
        if not ok:
            local.unlink(missing_ok=True)  # else the next pass "defaults to existing file"
        with lock:
            (verified if ok else failed).append(path)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, paths))
    return verified, failed, waits, errors


def restore(repo: str, local_dir: str, sleep=time.sleep, api=None,
            budget_seconds: float = DEFAULT_BUDGET_MINUTES * 60,
            clock=time.monotonic, workers: int = MAX_WORKERS, download=None,
            bulk=git_bulk_fetch) -> str:
    target = Path(local_dir)
    if target.exists() and any(target.iterdir()):
        raise RuntimeError(f"{target} is not empty; restore only into an empty directory.")
    api = api or HfApi()
    download = download or hf_hub_download
    deadline = clock() + budget_seconds

    def wait_or_fail(seconds: float, why: str) -> None:
        left = deadline - clock()
        if left <= 0 or seconds > left:
            raise RuntimeError(
                f"Corpus restore failed: {budget_seconds / 60:.0f}-minute budget spent ({why})"
            )
        print(f"  waiting {seconds:.0f}s ({left / 60:.1f} min of budget left)", file=sys.stderr)
        sleep(seconds)

    sha = None
    remote = None
    while remote is None:
        try:
            if sha is None:
                sha = api.repo_info(repo_id=repo, repo_type="dataset").sha
                if not sha:
                    raise RuntimeError(f"could not resolve head sha for {repo}")
            remote = _remote_files(api, repo, sha)
        except Exception as exc:  # noqa: BLE001
            if "could not resolve head sha" in str(exc):
                raise
            wait = rate_limit_wait(exc)
            print(f"Listing {repo} failed: {exc}", file=sys.stderr)
            wait_or_fail(wait if wait is not None else ERROR_BACKOFF_SECONDS, str(exc))

    print(f"Restoring {len(remote)} files from {repo}@{sha}", file=sys.stderr)
    done: set[str] = set()
    if bulk is not None:
        started = clock()
        try:
            bulk(repo, sha, target, include=_ALLOW_PATTERNS)
        except Exception as exc:  # noqa: BLE001 - the per-file loop covers whatever is missing
            detail = getattr(exc, "stderr", "") or ""
            print(f"git bulk fetch failed, falling back to per-file: {exc} {detail[-500:]}",
                  file=sys.stderr)
        # The checkout holds the whole dataset; keep only what the build reads.
        for path in target.rglob("*"):
            rel = path.relative_to(target).as_posix()
            if path.is_file() and rel not in remote:
                path.unlink()
        bad = {p for p, _reason in _problems(target, remote)}
        for path in bad:
            (target / path).unlink(missing_ok=True)  # e.g. pointer files from a failed lfs pull
        done = {p for p in remote if p not in bad}
        print(f"git bulk fetch: {len(done)}/{len(remote)} verified, {len(bad)} to fetch per file "
              f"({clock() - started:.0f}s)", file=sys.stderr)
    pass_no = 0
    while True:
        todo = [p for p in sorted(remote) if p not in done]
        if not todo:
            problems = _problems(target, remote)
            if not problems:
                print(f"Verified {len(remote)} files against {repo}@{sha} in {pass_no} pass(es)")
                return local_dir
            for path, _reason in problems:
                (target / path).unlink(missing_ok=True)
                done.discard(path)
            continue
        pass_no += 1
        verified, failed, waits, errors = _fetch_pass(
            repo, sha, target, todo, remote, download, workers
        )
        done.update(verified)
        print(
            f"Pass {pass_no}: {len(verified)} verified this pass, {len(done)}/{len(remote)} "
            f"total, {len(remote) - len(done)} remaining; {len(failed)} mismatched, "
            f"{len(waits)} rate-limited, {len(errors)} other errors",
            file=sys.stderr,
        )
        if errors:
            print(f"  e.g. {errors[:3]}", file=sys.stderr)
        if len(done) == len(remote):
            continue
        if waits:
            wait_or_fail(max(waits), f"{len(remote) - len(done)} files still missing, rate-limited")
        elif not verified:
            sample = (errors or [f"{p}: content differs" for p in failed])[:3]
            wait_or_fail(ERROR_BACKOFF_SECONDS, f"{len(remote) - len(done)} files missing or mismatched, e.g. {sample}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="cchew/lex-au", help="HF dataset repo")
    parser.add_argument("--local-dir", default="corpus")
    parser.add_argument("--no-git", action="store_true",
                        help="Skip the git bulk fetch and download every file individually.")
    parser.add_argument(
        "--budget-minutes", type=float,
        default=float(os.environ.get("LEXAU_RESTORE_BUDGET_MINUTES") or DEFAULT_BUDGET_MINUTES),
        help="Total wall-clock budget including rate-limit waits "
             "(env LEXAU_RESTORE_BUDGET_MINUTES; default %(default)s).",
    )
    args = parser.parse_args()

    started = time.monotonic()
    path = restore(args.repo, args.local_dir, budget_seconds=args.budget_minutes * 60,
                   bulk=None if args.no_git else git_bulk_fetch)
    print(f"Restored corpus from {args.repo} -> {path} in {time.monotonic() - started:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
