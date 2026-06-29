# lex-au-graph

Cross-reference knowledge graph over Australian Commonwealth legislation.

Layer 2.5 of the AU Legislative Intelligence Stack: sits between [lex-au](https://github.com/cchew/lex-au) (AKN XML corpus) and lex-au-search (hybrid vector search), providing graph-based definition resolution and cross-reference traversal that flat vector search cannot reliably handle.

**Status: v0.6.0**

## Stack position

```
Layer 1: lex-au          — AKN 3.0 XML corpus
Layer 2: lex-au-search   — hybrid vector search + MCP
Layer 2.5: lex-au-graph  — cross-reference graph + definition resolution (this repo)
Layer 3: ClauseKit        — machine-readable rule extraction
```

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
lexaugraph build --corpus-dir /path/to/lex-au/corpus/

# Print graph statistics
lexaugraph stats

# Resolve a defined term
lexaugraph resolve --term "personal information" --act "/akn/au/act/1988/119"

# Start the MCP server
lexaugraph serve
```

## MCP server

```bash
lexaugraph serve --graph graph.json
```

Registers four tools on a FastMCP server. Connect via any MCP client (Claude Desktop, Claude Code, etc.).

## Versions

- **v0.6.0** — 2026-06-29: Two new MCP tools — `find_all_definitions` (cross-Act term search) and `get_act_terms` (alphabetical term index per Act). 52 tests.
- **v0.5.0** — 2026-06-27: XPath extraction over AKN `<term>`/`<def>` markup — 2,395 defined terms (+73% over v0.4.0, up from 1,385).
- **v0.4.0** — 2026-06-22: First release — corpus loader, graph builder, definition resolver, FastMCP server, Typer CLI.

## Known limits (v0.6.0)

- `<ref>` cross-references are pattern-matched; unusual citation forms may be missed.
- `find_all_definitions` returns results in graph iteration order (non-deterministic across rebuilds if node insertion order changes).
- Graph is a static snapshot; re-run `lexaugraph build` after corpus updates.

## License

MIT — see [LICENSE](LICENSE).
