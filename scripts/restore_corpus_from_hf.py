"""Restore the published lex-au corpus from Hugging Face into a local
directory, so this repo's build pipeline has something to build against
in a fresh CI checkout (corpus/ is not checked into this repo).

Unlike lex-au's own restore_corpus_from_hf.py, this does not write a sync
stamp -- that mechanism exists to let lex-au's export-hf reconcile remote
deletions against a local corpus it also writes back to. This repo only
ever reads the corpus; it never exports back to cchew/lex-au.

allow_patterns restricts the download to what lexaugraph build actually
reads (index.json + xml/*.xml, ~3,085 files). Found necessary the hard way
(2026-09-29): cchew/lex-au publishes 11,387 files total (xml/ + reports/ +
images/ + index.json), and an unfiltered snapshot_download from a GitHub
Actions runner hit Hugging Face's HTTP 429 rate limit around 79% through
the download, entered a 285s backoff, and got killed by the workflow's
30-minute timeout before the restore step -- let alone the actual
build/centrality/complexity steps -- ever finished.
"""
from __future__ import annotations

import argparse
import sys

from huggingface_hub import snapshot_download

_ALLOW_PATTERNS = ["index.json", "xml/*.xml"]


def restore(repo: str, local_dir: str) -> str:
    return snapshot_download(
        repo_id=repo, repo_type="dataset", local_dir=local_dir, allow_patterns=_ALLOW_PATTERNS
    )


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
