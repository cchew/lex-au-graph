"""Validate signal 1 (LLM codifiability tag) against ClauseKit's 262 hand-tagged
provisions across 5 domains (eu-ai-act, ndb, privacy-apps, sis-death-benefits,
ssa-bereavement).

ClauseKit's rules don't store raw provision text -- only docref metadata
(source_doc, article) and a paraphrased "obligation" summary. This script
resolves each rule's real section text from lex-au-graph's own loaded corpus
(matching by Act title and section number via docref.source_doc/docref.article),
so the comparison is against the same real text signal 1 scores in production,
not ClauseKit's paraphrase.

Real cost: 262 Batch API calls on Haiku 4.5, well under $1 (~$0.33 estimated) --
see docs/superpowers/specs/2026-08-05-codifiability-scoring-design.md's
Validation section. Two ClauseKit domains are near-degenerate for a per-domain
confusion matrix: ndb has zero "high" labels (0/54), sis-death-benefits has
only 1/50 "high" -- flagged in the output, not hidden.

Usage:
    python scripts/codifiability_clausekit_validation.py \
        --graph graph.json \
        --rules-dir ../../clause-kit/repo/rules \
        --output codifiability_clausekit_validation_results.json
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import anthropic

from lexaugraph.codifiability import (
    _SIGNAL1_SYSTEM_PROMPT,
    build_batch_requests,
    build_signal1_prompt,
    submit_batch,
    wait_for_batch,
    fetch_batch_results,
)
from lexaugraph.graph import LexAuGraph


def load_clausekit_rules(rules_dir: Path) -> list[dict]:
    """Flatten all rules across all *.json files in rules_dir into one list,
    each annotated with its source domain filename (stem)."""
    all_rules = []
    for path in sorted(rules_dir.glob("*.json")):
        data = json.loads(path.read_text())
        for rule in data.get("rules", []):
            rule = dict(rule)
            rule["_domain"] = path.stem
            all_rules.append(rule)
    return all_rules


def resolve_rule_text(rule: dict, graph: LexAuGraph) -> str | None:
    """Resolve a ClauseKit rule's real section text from the loaded graph, via
    docref.source_doc (Act title, exact match) and docref.article (section
    number, matched against the graph's own section-number index). Returns None
    if the Act or section can't be found in the loaded corpus."""
    docref = rule.get("docref", {})
    source_doc = docref.get("source_doc")
    article = docref.get("article")
    if not source_doc or not article:
        return None

    act_frbr_uri = None
    for node_id, data in graph.graph.nodes(data=True):
        if data.get("type") == "act" and data.get("title") == source_doc:
            act_frbr_uri = node_id
            break
    if act_frbr_uri is None:
        return None

    section_id = graph._section_number_index.get(act_frbr_uri, {}).get(article)
    if section_id is None:
        return None
    return graph.graph.nodes[section_id].get("text")


def run_validation(rules: list[dict], graph: LexAuGraph, client: anthropic.Anthropic) -> dict:
    resolved: list[tuple[dict, str]] = []
    unresolved_count = 0
    for rule in rules:
        text = resolve_rule_text(rule, graph)
        if text is None:
            unresolved_count += 1
            continue
        resolved.append((rule, text))

    items = [(rule["rule_id"], text) for rule, text in resolved]
    requests, id_map = build_batch_requests("clausekit_validation", items, _SIGNAL1_SYSTEM_PROMPT, build_signal1_prompt)
    batch_id = submit_batch(requests, client)
    wait_for_batch(batch_id, client)
    results = fetch_batch_results(batch_id, client, id_map)

    confusion: dict[str, dict[str, int]] = {}
    per_domain_confusion: dict[str, dict[str, dict[str, int]]] = {}
    agree_count = 0
    scored_count = 0
    batch_failed_count = 0
    for rule, _text in resolved:
        our_result = results.get(rule["rule_id"])
        if our_result is None:
            batch_failed_count += 1
            continue
        scored_count += 1
        their_tag = rule["codifiability"]
        our_tag = our_result["tag"]
        confusion.setdefault(their_tag, {}).setdefault(our_tag, 0)
        confusion[their_tag][our_tag] += 1
        domain = rule["_domain"]
        per_domain_confusion.setdefault(domain, {}).setdefault(their_tag, {}).setdefault(our_tag, 0)
        per_domain_confusion[domain][their_tag][our_tag] += 1
        if our_tag == their_tag:
            agree_count += 1

    return {
        "total_rules": len(rules),
        "unresolved_count": unresolved_count,
        "scored_count": scored_count,
        "batch_failed_count": batch_failed_count,
        "agreement_rate": agree_count / scored_count if scored_count else None,
        "confusion_matrix": confusion,
        "per_domain_confusion_matrix": per_domain_confusion,
        "degenerate_domains_note": (
            "ndb has zero 'high' labels (0/54) and sis-death-benefits has only 1/50 "
            "'high' -- their per-domain rows are uninformative for medium/high "
            "discrimination specifically, per the design spec's Validation section."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=Path("graph.json"))
    parser.add_argument("--rules-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("codifiability_clausekit_validation_results.json"))
    args = parser.parse_args()

    graph = LexAuGraph.load(args.graph)
    rules = load_clausekit_rules(args.rules_dir)
    client = anthropic.Anthropic()
    results = run_validation(rules, graph, client)

    args.output.write_text(json.dumps(results, indent=2))
    print(f"Total ClauseKit rules: {results['total_rules']}, resolved to real text: {results['scored_count']}, unresolved: {results['unresolved_count']}, batch failed: {results['batch_failed_count']}")
    print(f"Agreement rate: {results['agreement_rate']}")


if __name__ == "__main__":
    main()
