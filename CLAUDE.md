# lex-au-graph

Retrieval layer of the AU Legislative Intelligence Stack. Cross-reference knowledge graph over the lex-au AKN 3.0 XML corpus.

## Stack position

Corpus: lex-au (../lex-au/repo/) — AKN 3.0 XML corpus
Retrieval: lex-au-search (../lex-au-search/repo/) — hybrid search API + MCP; lex-au-graph (this repo) — cross-reference graph + definition resolution
Applications: ClauseKit (../clause-kit/repo/) — rule extraction; term-comparison (../term-comparison/repo/) — IM2026 definition-comparison bot, built directly on this repo's DefinitionResolver

## Setup

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

## CLI

lexaugraph build --corpus-dir ../../lex-au/repo/corpus/
lexaugraph stats [--graph graph.json]
lexaugraph resolve --term TERM --act FRBR_URI [--graph graph.json]
lexaugraph centrality [--graph graph.json] [--output centrality.json]
lexaugraph impact --eid EID --act FRBR_URI [--max-hops 3] [--graph graph.json]
lexaugraph serve [--graph graph.json]

## Tests

pytest

## Graph format

NetworkX DiGraph persisted as JSON via node_link_data/node_link_graph.
Default output: graph.json in the working directory.
