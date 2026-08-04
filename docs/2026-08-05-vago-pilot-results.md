# VAGO codifiability pilot — results

**Date:** 2026-08-05
**Gates:** item #4 of the 2026-07-31 six-item scoping session (codifiability/complexity scoring)
**Verdict: fails the go/no-go bar. Do not build signal 2 (VAGO vagueness) on this dataset as scoped.**

## What was tested

`docs/2026-07-22-codifiability-scoring-research.md` flagged VAGO's English variant as an unvalidated transfer risk — a neural clone trained on French press text (FreSaDa), no legal-domain or Australian-English exposure — and called for a cheap pilot before committing engineering time: run it against already hand-labelled EU AI Act/NDB rules from ClauseKit and eyeball agreement.

No public pip package or importable model exists for VAGO. It's a hosted research demo (Institut Jean-Nicod / Mondeca, DIEKB project, funded by the French DGA) at `research.mondeca.com/demo/vago/`. Found and called its underlying CAM workflow API (`DIEKB_vagueness_spacy_en.xml`) directly via browser network inspection — same endpoint the demo's own "Test it" button calls, undocumented but public, no auth. Script: `scripts/vago_codifiability_pilot.py`. Raw output: `vago_pilot_results.json`.

**Sample:** 20 rules — 5 each of EU AI Act `codifiability: low/medium/high` plus 5 NDB `low` (NDB has near-zero label variance, included as a sanity floor, not a real test of discrimination).

## Result

Every single sample — regardless of `low`/`medium`/`high` codifiability label — scored `meanRatioVague: 1.0`. Zero discrimination across all three labels:

| codifiability | n | mean VAGO vagueness ratio |
|---|---|---|
| low | 10 | 1.000 |
| medium | 5 | 1.000 |
| high | 5 | 1.000 |

## Sanity check (API isn't broken)

Ran three hand-picked control sentences outside the legal corpus to confirm the API itself discriminates on ordinary text:

| text | meanRatioVague |
|---|---|
| "The Act commenced on 1 January 2020." | 0.0 (precise) |
| "Reasonable steps should generally be taken where appropriate." | 1.0 (vague, correctly) |
| "A person who is 18 years of age or older may apply for registration under section 6." | 1.0 |

The third control is the diagnostic one: a textbook precise, highly codifiable legal rule (clear threshold, clear modality) scored fully vague. VAGO's per-sentence classifier is binary (a sentence is "vague" if it contains *any* trigger term), and ordinary legal-drafting syntax — disjunctive conditions ("or"), deontic modals ("may", "shall"), qualifying adjectives — trips the same lexical markers VAGO uses to detect journalistic hedging and subjectivity. This isn't sampling noise; it's a structural mismatch between what VAGO's lexicon was built to catch (press-text vagueness/opinion markers) and what dense, connective-heavy statutory drafting looks like.

## What this does and doesn't rule out

- **Rules out:** using VAGO's document/sentence-level vague-vs-precise classification as signal 2 of the codifiability composite, on this text style, without further work. It saturates at "vague" for essentially all real legislative provisions, precise or not.
- **Doesn't rule out:** the underlying numeric sub-scores (`ratioVC`/`ratioVG`/`ratioVA`/`ratioVD`, `meanRatioPrecis`) showed some spread (0.0–0.095) that wasn't obviously label-correlated in this sample, but 20 rows is too small to confirm or deny a weaker continuous signal exists underneath the saturated binary one. Not pursued further here — that would be a second, larger pilot, not a conclusion this cheap check was chartered to reach.
- **Doesn't touch** signal 3 (RegData/QuantGov prescriptive-language density) or the ALRC indeterminate-concept/conditional-statement metrics from the 2026-07-23 addendum — those are separate, still-untested signals for the same composite.

## Recommendation

Don't build VAGO integration for item #4 as originally scoped. If codifiability scoring is picked up again, either drop signal 2 entirely and rely on signals 1 (LLM tag, already have via ClauseKit) and 3 (prescriptive-density, format-agnostic, not yet tested), or replace VAGO with a vagueness/open-texture measure built or fine-tuned specifically for legal drafting rather than press text — a different, larger effort than this pilot.
