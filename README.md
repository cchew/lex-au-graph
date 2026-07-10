# lex-au-graph

Cross-reference knowledge graph over Australian Commonwealth legislation.

Retrieval layer of the AU Legislative Intelligence Stack, alongside lex-au-search: sits between [lex-au](https://github.com/cchew/lex-au) (AKN XML corpus) and the search/rules/application layers, providing graph-based definition resolution and cross-reference traversal that flat vector search cannot reliably handle.

**Status: v0.7.1**

## Stack position

```
Corpus:       lex-au         — AKN 3.0 XML corpus
Retrieval:    lex-au-search  — hybrid vector search + MCP
              lex-au-graph   — cross-reference graph + definition resolution (this repo)
Applications: ClauseKit       — machine-readable rule extraction
              term-comparison — IM2026 definition-comparison bot, built directly on this repo's DefinitionResolver
```

Call-order note: for queries about what a term means or how it's defined across Acts, this repo is the authoritative source — check it before or alongside lex-au-search, which can otherwise match the wrong Act's use of a homonymous term.

## What it does

Builds a directed graph over the lex-au AKN corpus:

- **Nodes:** Act, Section, DefinedTerm
- **Edges:** `contains` (Act→Section), `ref` (Section→Section/Act), `defines` (Section→DefinedTerm)

Exposes four MCP tools:

- `resolve_definition(term, act_frbr_uri)` — canonical definition text and section citation for a defined term within an Act
- `cross_references(eid, act_frbr_uri)` — all outgoing cross-references from a section
- `find_all_definitions(term)` — all definitions of a term across all loaded Acts (useful when the Act is unknown or a term is defined in multiple Acts)
- `get_act_terms(act_frbr_uri)` — all defined terms in an Act, sorted alphabetically

## Motivation

Defined term chains in AU legislation span Acts. "Income support payment" in the Social Security Act 1991, for example, references a definition that in turn cross-references the Superannuation Industry (Supervision) Act 1993. Flat vector search returns sections ranked by semantic similarity but cannot reliably traverse these chains. A graph layer makes them deterministic.

## Attribution

Inspired by [i-dot-ai/lex-graph](https://github.com/i-dot-ai/lex-graph) (MIT, Copyright 2025 i.AI), the UK Government AI Incubator's equivalent project over UK legislation. lex-au-graph is independently implemented for Australian AKN 3.0 XML, following the same architectural pattern (NetworkX + MCP server) but adapted for AU citation syntax, FRBR URI conventions, and the lex-au corpus format.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## CLI

```bash
# Build the graph from a lex-au corpus
# Also writes citation_candidates.json (Acts cited but not yet in the corpus)
# and prints a tagged/untagged citation resolution stats breakdown
lexaugraph build --corpus-dir /path/to/lex-au/corpus/

# Print graph statistics
lexaugraph stats

# Resolve a defined term
lexaugraph resolve --term "personal information" --act "/akn/au/act/1988/119"

# Backfill untagged prose definitions for one Act via grounded LLM extraction
lexaugraph extract-untagged --xml /path/to/act.xml --act-frbr-uri "/akn/au/act/1988/119"

# Start the MCP server
lexaugraph serve
```

## MCP server

```bash
lexaugraph serve --graph graph.json
```

Registers four tools on a FastMCP server. Connect via any MCP client (Claude Desktop, Claude Code, etc.).

## Versions

- **v0.7.1** — 2026-07-10: Fixed `_CITATION_PATTERN` dropping the leading word(s) of titles containing a curly apostrophe (U+2019, e.g. "Veterans’ Entitlements Act 1986") — the regex word-char class only allowed the straight apostrophe. 105 tests.
- **v0.7.0** — 2026-07-10: Cross-Act citation resolution and untagged-definition recovery. (1) Fixed a title-normalization bug where 120+ already-tagged `<ref href="">Act Title Year</ref>` citations silently failed to resolve; added a regex pass over untagged prose citations; unresolved citations (Acts not yet in the corpus) are now written to `citation_candidates.json` instead of silently dropped — no stub/placeholder nodes. (2) New `extract-untagged` CLI command backfills untagged prose definitions (no AKN `<term>`/`<def>` markup) into an existing graph via grounded LLM extraction with byte-exact verification against source text. 104 tests.
- **v0.5.0** — 2026-06-27: XPath extraction over AKN `<term>`/`<def>` markup — 2,395 defined terms (+73% over v0.4.0, up from 1,385).
- **v0.4.0** — 2026-06-22: First release — corpus loader, graph builder, definition resolver, FastMCP server, Typer CLI.

## Known limits (v0.7.0)

- `<ref>` cross-references and untagged prose citations are both pattern-matched; unusual citation forms may still be missed. `citation_candidates.json` is a best-effort corpus-expansion signal, not a guarantee of completeness.
- `find_all_definitions` returns results in graph iteration order (non-deterministic across rebuilds if node insertion order changes).
- Graph is a static snapshot; re-run `lexaugraph build` after corpus updates.

## License

MIT — see [LICENSE](LICENSE).
