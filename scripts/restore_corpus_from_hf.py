"""Restore the published lex-au corpus from Hugging Face into a local
directory, so this repo's build pipeline has something to build against
in a fresh CI checkout (corpus/ is not checked into this repo).

This repo only reads the corpus; it never exports back to cchew/lex-au,
so there is no sync stamp to write.

allow_patterns restricts the download to what lexaugraph build actually
reads (index.json + xml/*.xml, ~3,085 files). Found necessary the hard way
(2026-09-29): cchew/lex-au publishes 11,387 files total, and an unfiltered
snapshot_download from a GitHub Actions runner hit HF's 429 rate limit and
the workflow's 30-minute timeout.

Pinned and verified (2026-10-26, after lex-au's 2026-10-25 clobber): under
429s snapshot_download can log "Defaulting to existing file" and keep
whatever is already on disk. So the target must be empty, the head sha is
resolved once and every file comes from that revision, and each file is
checked against the revision's tree (LFS sha256 or git blob sha1).
Mismatches are deleted and re-fetched with backoff; the script exits
non-zero if any remain.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.utils import filter_repo_objects

_ALLOW_PATTERNS = ["index.json", "xml/*.xml"]
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 30
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


def restore(repo: str, local_dir: str, sleep=time.sleep, api=None) -> str:
    target = Path(local_dir)
    if target.exists() and any(target.iterdir()):
        raise RuntimeError(f"{target} is not empty; restore only into an empty directory.")
    api = api or HfApi()

    sha = None
    remote = None
    last_error = "unknown"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            if sha is None:
                sha = api.repo_info(repo_id=repo, repo_type="dataset").sha
                if not sha:
                    raise RuntimeError(f"could not resolve head sha for {repo}")
            if remote is None:
                remote = _remote_files(api, repo, sha)
            snapshot_download(
                repo_id=repo,
                repo_type="dataset",
                revision=sha,
                local_dir=local_dir,
                allow_patterns=_ALLOW_PATTERNS,
            )
            problems = _problems(target, remote)
            if not problems:
                print(f"Verified {len(remote)} files against {repo}@{sha}")
                return local_dir
            for path, _reason in problems:
                (target / path).unlink(missing_ok=True)
            sample = [f"{p}: {r}" for p, r in problems[:3]]
            last_error = f"{len(problems)} files missing or mismatched, e.g. {sample}"
        except Exception as exc:  # noqa: BLE001 - retry any transport failure
            last_error = str(exc)
        print(f"Restore attempt {attempt}/{MAX_ATTEMPTS} incomplete: {last_error}", file=sys.stderr)
        if attempt < MAX_ATTEMPTS:
            sleep(BACKOFF_SECONDS * attempt)
    raise RuntimeError(f"Corpus restore failed after {MAX_ATTEMPTS} attempts: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="cchew/lex-au", help="HF dataset repo")
    parser.add_argument("--local-dir", default="corpus")
    args = parser.parse_args()

    path = restore(args.repo, args.local_dir)
    print(f"Restored corpus from {args.repo} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
