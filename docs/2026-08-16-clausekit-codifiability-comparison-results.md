# ClauseKit codifiability comparison — results

**Date:** 2026-08-16
**Gates:** signal 1 validation item in `docs/superpowers/specs/2026-08-05-codifiability-scoring-design.md`
**Verdict: not a validation result. Document as an experiment, don't cite it as evidence signal 1 is accurate — not in the design spec, not in the README, not anywhere public.**

## What was tested

The design spec's Validation section called for re-running signal 1 (Haiku 4.5 codifiability tag) against ClauseKit's 262 provisions and reporting a raw agreement rate plus confusion matrix, describing ClauseKit's `codifiability` field as "hand-tagged" ground truth.

That description is wrong. Checked ClauseKit's source before trusting it: `clause-kit/repo/src/extract.py` shows the `codifiability` field is itself LLM-assigned — Claude Opus 4.8, during the extraction pipeline (`python -m src.pipeline --domain X`), per the system prompt ("If a rule cannot be expressed as a deterministic condition... set codifiability to low"). The domain `*.REVIEW.md` files are titled "Extraction Review" and their stated purpose is reviewing JSON Logic *condition* correctness before committing, not re-labeling codifiability. One later commit (`ad9849f`, 2026-06-19, Ching + Claude co-authored) patched a batch of "codifiability/condition mismatches" — an internal consistency fix (e.g. `condition: null` should imply `low`), not an independent legal re-annotation.

So this comparison is signal 1 (Haiku 4.5, lex-au-graph's prompt) vs. ClauseKit's own LLM tag (Opus 4.8, a different prompt), with a thin human review layer on ClauseKit's side that targeted rule logic, not the codifiability label. Two independently-prompted LLMs, not an LLM against ground truth.

Separately, a real open-source golden dataset for this task (AU legislative provisions labeled by codifiability/determinism, human-annotated) was searched for and doesn't exist. Closest adjacent resources — none directly usable: LegalDiscourse/StateCensusLaws.org (US state law, discourse-annotated, κ>0.8, but wrong jurisdiction and wrong label schema), CODE-ACCORD (UK/Finland building regs, human-annotated, but wrong domain), OpenExempt (US bankruptcy benchmark that curates out subjective-standard provisions by design, but not a labeled corpus to correlate against).

## Method

`scripts/codifiability_clausekit_validation.py` resolves each ClauseKit rule's real section text from lex-au-graph's own loaded corpus (via `docref.source_doc`/`docref.article`, matched against the graph's section-number index — required a bug fix first, see below), scores it with signal 1's actual production prompt via the Anthropic Batch API, and compares to ClauseKit's stored tag.

**Bug found and fixed en route:** `LexAuGraph.load()` deserialized the graph but never rebuilt `_title_index`/`_section_number_index` — two lookup dicts populated during `add_act_data()`, not part of the persisted graph itself. Any script loading a saved `graph.json` (rather than building fresh) got empty indexes and zero resolved rules. Fixed via a `_rebuild_indexes()` call in `load()` (`src/lexaugraph/graph.py`). Confirmed no regression: `pytest -k "load or graph"`, 70 passed.

**Cost:** 262 Batch API calls, Haiku 4.5, ~$0.33 (matches the design spec's estimate).

## Result

262 total ClauseKit rules. 153 resolved to real corpus text (eu-ai-act's 32 are EU law, not in the AU corpus by design; privacy-apps' 77 cite APP numbers rather than section numbers, not covered by the section-number index — both correctly out of scope, not a bug).

**Raw agreement: 34.6%** (53/153).

Confusion matrix (rows = ClauseKit's tag, columns = signal 1's tag):

| ClauseKit \ signal 1 | low | medium | high |
|---|---|---|---|
| low (n=106) | 42 | 22 | **42** |
| medium (n=37) | 7 | 3 | **27** |
| high (n=10) | 0 | 2 | 8 |

The disagreement is one-directional: signal 1 systematically over-calls "high" relative to ClauseKit — 40% of ClauseKit's "low" rows and 73% of ClauseKit's "medium" rows got tagged "high" by signal 1. The "high" row itself is the only place signal 1 looks reliable (8/10), but n=10 is too small to trust.

Per the design spec's advance warning, `ndb` (0/54 "high") and `sis-death-benefits` (1/50 "high") are near-degenerate for per-domain medium/high discrimination — confirmed in this doc's companion `2026-08-16-clausekit-codifiability-comparison-results.json`'s `per_domain_confusion_matrix`, not hidden.

## What this does and doesn't rule out

- **Doesn't validate signal 1** against ground truth — none exists for this task, open-source or otherwise (see the golden-dataset search above).
- **Does show** two independently-prompted LLMs (different model, different prompt) disagree substantially on codifiability judgment for the same AU legal text, with signal 1 biased toward over-optimistic "high" calls specifically. That's real evidence signal 1's current prompt may be too permissive on what counts as "deterministic" — worth a prompt-tuning pass — but it's evidence from a second opinion, not a graded exam.
- **Doesn't touch** signal 2 (LLM vagueness tag) or signal 3 (regex prescriptive density) — those remain as scoped in the design spec: signal 2 has no ground truth to validate against at all (novel), signal 3 is separately validated against ALRC/RDAU1.0 real external data (see `complexity_validation_pilot.py`'s sibling run, 1,026 Acts, Pearson 0.80–0.98).

## Recommendation

Don't cite this comparison as validation anywhere — design spec, README, MCP tool docstrings. The honest framing for signal 1 going forward: an LLM heuristic tag, cross-checked internally via `compute_agreement()` against signal 2 and signal 3 (one of which, signal 3, is non-LLM and so not subject to shared-model bias), not externally validated against human-labeled ground truth. If real ground truth is wanted later, it requires building a small hand-annotated AU sample directly — multiple annotators, reported κ, same rigor as LegalDiscourse's US-law annotation — not found off the shelf.
