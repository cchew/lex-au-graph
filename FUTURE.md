# lex-au-graph — follow-ups

Stack-wide roadmap: [lex-au's `FUTURE.md`](https://github.com/cchew/lex-au/blob/main/FUTURE.md).
This file tracks lex-au-graph-owned items.

## Loader: capture the `<term>` tail alongside `<def>` — problem 1 RESOLVED v0.12.2 (2026-09-08)

**Raised:** 2026-09-08, from the lex-au-explorer defined-term-highlighting Task 0 spike
(`../../lex-au-explorer/docs/superpowers/notes/2026-09-08-termhighlight-spike.md`).

`_extract_defined_terms` (`src/lexaugraph/loader.py`) stored only
`"".join(def_el.itertext())` — the `<def>` element's text. Two problems were observed
across the ~29,338 `defined_term` nodes:

1. **Pointer / operator phrasing was lost — FIXED.** The operator that types a
   definition (`means`, `includes`, `has the meaning given by`, `has the same meaning
   as`) sits in the `<term>` element's *tail* (text after `</term>`, before `<def>`),
   outside `<def>`, so `definition_text` never contained it. ~11,400 of 29,250 tagged
   terms use a non-`means` operator; an inclusive or pointer definition was stored as
   if exhaustive. `_extract_defined_terms` now normalises `term_el.tail` and prepends
   it: `"includes the external Territories."`, `"has the meaning given by section 4."`.
   Loader tests: `test_defined_term_definition_text_keeps_{means,inclusive,pointer}_operator`
   + fixture `tests/fixtures/term-operator-sample.xml`. `graph.json` must be
   regenerated for the change to reach the deployed graph and its consumers.

2. **Term-boundary bleed — NOT a graph-loader bug; reassigned to lex-au.** In
   `corporations-act-2001.xml` the `<def>` for `borrow` is drawn too wide in the
   source AKN and swallows the definitions of `borrower`, `borrowed`, and `business
   affairs` (each marked `<b><i>…</i></b>` inline, not `<term>`). `def_el.itertext()`
   is already bounded to the `<def>` subtree — the boundary is wrong *in the source
   XML*, so lex-au-graph cannot fix it without heuristically re-splitting `<def>`
   content. This is the same bold/italic-definiendum class as Gap 1 below and belongs
   in lex-au's `termlinks.py` / `<def>`-scoping logic. Tracked in lex-au's `FUTURE.md`.
   Only known instance in the current corpus.

**Downstream:** lex-au-explorer Task 2 (cross-Act definition follow) can now detect
pointer definitions off `definition_text`. `_follow_cross_act` was previously inert
because the `^`-anchored pointer regex matched 0 nodes; with the operator prepended it
has signal. Consumers must rebuild `graph.json`: lex-au-explorer, term-comparison
(Act Alike — redeployed 2026-09-08), ClauseKit (deferred, logged to its `FUTURE.md`).

## Gap 1: `termlinks.py` extraction coverage (lex-au-owned, tracked here for the graph impact)

The graph covers ~29% of Acts (894 / 3,076) because it inherits lex-au's `<term>`/`<def>`
markup. The Task 0 spike confirmed the missing population is **not** Acts with zero
defined terms (those are mostly disguised amendment Acts with no own definitions) — it is
extraction quality *inside* the 894 covered Acts: bold/italic-formatted definienda,
`<ref>`-bearing pointer definitions, and "in relation to"-qualified definiens that
lex-au's `inject_terms` / `inject_list_defs` currently skip. A non-LLM enrichment wired
into `lexaugraph build` was assessed (spike 0a) and rejected: it flips ~5 of 81 real gap
Acts for ~9 new nodes. The lever is the lex-au pattern rewrite, not a graph-build step.
