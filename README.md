# lex-au-graph

Cross-reference knowledge graph over Australian Commonwealth legislation, for definition resolution and cross-reference traversal that flat vector search cannot reliably handle.

> [!NOTE]
> [search.gov.au](https://search.gov.au)'s Align stream ("Common Ground", Department of Finance, alpha — see [Government content is AI food](https://www.youtube.com/watch?v=X5UAWFl7-FE), APS Digital Profession Innovation Month, July 2026) tackles the same problem at whole-of-government scale: surfacing linkage and divergence across Acts and agencies.

**Status: v0.11.0**

## Uses / used by

- **Depends on:** [lex-au](https://github.com/cchew/lex-au) (AKN 3.0 XML corpus as the input)
- **Related:** [lex-au-search](https://github.com/cchew/lex-au-search) (hybrid vector search + MCP; for queries about what a term means or how it's defined across Acts)
- **Used by:** [ClauseKit](https://github.com/cchew/clause-kit) (run claims against extracted legislation rules, grounded back to source clauses), term-comparison (compare how terms are defined across Acts)

Full stack map: [lex-au-search's `STACK.md`](https://github.com/cchew/lex-au-search/blob/main/STACK.md) and [lex-au's `FUTURE.md`](https://github.com/cchew/lex-au/blob/main/FUTURE.md).

## What it does

Builds a directed graph over the lex-au AKN corpus:

- **Nodes:** Act, Section, DefinedTerm
- **Edges:** `contains` (Act→Section), `ref` (Section→Section/Act — each carries one or more classified citations: `amends`/`repeals`/`cites`/`references_definition`, with a relation-confidence and an extraction-confidence score per citation), `defines` (Section→DefinedTerm)

Exposes four MCP tools:

- `resolve_definition(term, act_frbr_uri)` - canonical definition text and section citation for a defined term within an Act
- `cross_references(eid, act_frbr_uri)` - all outgoing cross-references from a section
- `find_all_definitions(term)` - all definitions of a term across all loaded Acts (useful when the Act is unknown or a term is defined in multiple Acts)
- `get_act_terms(act_frbr_uri)` - all defined terms in an Act, sorted alphabetically

## Motivation

Defined term chains in AU legislation span Acts. "Income support payment" in the Social Security Act 1991, for example, references a definition that in turn cross-references the Superannuation Industry (Supervision) Act 1993. Flat vector search returns sections ranked by semantic similarity but cannot reliably traverse these chains. A graph layer makes them deterministic.

## Linking back to legislation.gov.au

`ActNode.legislation_url` returns a working link to the Act/instrument's real page on legislation.gov.au (e.g. `https://www.legislation.gov.au/C2004A03712/latest/text`), built from `title_id` — an opaque register ID that comes from lex-au's corpus (`index.json`), not from the AKN FRBR URI (the two are unrelated; the FRBR URI's year/number cannot be used to derive `title_id`). Returns `None` if `title_id` wasn't available when the graph was built. Act-level only: legislation.gov.au does not expose stable per-section anchors, so there's no equivalent section-level deep link.

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

# Precompute PageRank centrality over the ref subgraph, writes centrality.json
lexaugraph centrality

# Show what's affected if a section changes (reverse-reachability fan-in)
lexaugraph impact --eid "part-I__sec-6" --act "/akn/au/act/1988/119"

# Backfill untagged prose definitions for one Act via grounded LLM extraction
lexaugraph extract-untagged --xml /path/to/act.xml --act-frbr-uri "/akn/au/act/1988/119"

# Start the MCP server
lexaugraph serve
```

## MCP server

```bash
lexaugraph serve --graph graph.json
```

Registers five tools on a FastMCP server. Connect via any MCP client (Claude Desktop, Claude Code, etc.).

## Versions

- v0.11.0 (2026-08-02): section-scoped `resolve_definition` (optional `section_eid` param), resolving in-Act term collisions by exact section, then nearest enclosing Part/Division, else unresolved rather than guessed. 228 tests.
- **v0.10.0** - `ActNode.title_id` and `legislation_url` - Act nodes now carry legislation.gov.au's opaque register ID (already present in lex-au's `index.json`, previously dropped by the graph loader) and a ready-to-use deep link (`https://www.legislation.gov.au/{title_id}/latest/text`). Act-level only - legislation.gov.au has no stable per-section anchor scheme (confirmed live: rendered text lives in a client-side EPUB blob with unstable, auto-generated Word bookmark ids, not semantic `#eId`-style anchors).
- **v0.9.0** - Legislative impact analysis: `impacted_by()` reverse-reachability fan-in ("what's affected if this section changes") and `compute_centrality()` PageRank triage over the ref subgraph. New `centrality`/`impact` CLI commands and `impact_analysis` MCP tool.
- **v0.8.0** - Intra-Act section citation extraction (bare section/subsection references, multi-section lists); persistent edge citation-frequency tracking; graph migrated to MultiDiGraph.
- **v0.7.3** - Fixed node_id collisions: same-Act terms with genuinely distinct meanings no longer silently overwrite each other (706 of 746 known collision pairs now survive as distinct nodes).
- **v0.7.2** - Fixed inline-formatting space bug that truncated citation matches.
- **v0.7.1** - Fixed citation pattern dropping leading words on curly-apostrophe titles.
- **v0.7.0** - Cross-Act citation resolution; untagged-definition recovery via grounded LLM extraction.
- **v0.5.0** - XPath extraction over AKN `<term>`/`<def>` markup, 2,395 defined terms.
- **v0.4.0** - First release - corpus loader, graph builder, definition resolver, FastMCP server, Typer CLI.

## Known limits

- `resolve_definition`/`find_all_definitions` return nothing for a term whose definiendum is bold/italic-formatted in the source DOCX - lex-au's term detection misses those (~46% of dictionary-style definitions corpus-wide). See [lex-au's Known limits](https://github.com/cchew/lex-au#known-limits).
- `<ref>` cross-references and untagged prose citations are both pattern-matched; unusual citation forms may still be missed. `citation_candidates.json` is a best-effort corpus-expansion signal, not a guarantee of completeness.
- Titles containing a lowercase preposition other than "of"/"and" (e.g. "Participants **in** British Nuclear Tests...") truncate to the portion after the preposition, since those words are deliberately excluded from the connector set to avoid over-matching surrounding prose (see comment above `_TITLE_CONNECTOR` in `citations.py`). A safe fix requires anchoring on `Act|Regulations|Rules <year>` and walking backward through title words, not a same-class one-line patch - deferred.
- `find_all_definitions` returns results in graph iteration order (non-deterministic across rebuilds if node insertion order changes).
- Graph is a static snapshot; re-run `lexaugraph build` after corpus updates.
- Relation classification (`amends`/`repeals`/`cites`/`references_definition`) uses a regex verb-proximity heuristic (±80-character window around each citation, excluding the citation's own text) with an opt-in LLM fallback for ambiguous cases (`lexaugraph build --llm-fallback`, off by default — real Anthropic API cost). Window size and confidence thresholds are a first-pass calibration, not independently validated against a labelled dataset — see `scripts/verify_relation_classification.py` for real-corpus sampling.

## License

MIT - see [LICENSE](LICENSE).
