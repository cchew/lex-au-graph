# lex-au-graph

Layer 2.5 of the AU Legislative Intelligence Stack. Cross-reference knowledge graph over the lex-au AKN 3.0 XML corpus.

## Stack position

Layer 1: lex-au (../lex-au/repo/) — AKN 3.0 XML corpus
Layer 2: lex-au-search (../lex-au-search/repo/) — hybrid search API + MCP
Layer 2.5: lex-au-graph (this repo) — cross-reference graph + definition resolution
Layer 3: ClauseKit (../clause-kit/repo/) — rule extraction

## Setup

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

## CLI

lexaugraph build --corpus-dir ../../lex-au/repo/corpus/
lexaugraph stats [--graph graph.json]
lexaugraph resolve --term TERM --act FRBR_URI [--graph graph.json]
lexaugraph serve [--graph graph.json]

## Tests

pytest

## Graph format

NetworkX DiGraph persisted as JSON via node_link_data/node_link_graph.
Default output: graph.json in the working directory.
