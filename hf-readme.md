---
license: cc-by-4.0
language:
- en
tags:
- law
- legislation
- australia
- knowledge-graph
- akn
pretty_name: lex-au-graph - Cross-reference graph over Commonwealth Acts
configs:
- config_name: default
  data_files:
  - split: train
    path: complexity.json
---

# lex-au-graph

Cross-reference knowledge graph over Australian Commonwealth Acts, built from
the [lex-au](https://huggingface.co/datasets/cchew/lex-au) AKN 3.0 XML corpus
— the retrieval layer of the AU Legislative Intelligence Stack.

This dataset publishes three files, rebuilt automatically whenever lex-au
publishes a corpus update:

- **`graph.json`** — the full cross-reference graph (nodes: Acts, Sections,
  defined terms; edges: contains, defines, ref, mentions), as NetworkX
  `node_link_data` JSON. Not tabular — load it directly, not via the dataset
  viewer:
  ```python
  import json, networkx as nx
  from huggingface_hub import hf_hub_download
  path = hf_hub_download("cchew/lex-au-graph", "graph.json", repo_type="dataset")
  graph = nx.node_link_graph(json.load(open(path)))
  ```
- **`centrality.json`** — PageRank centrality score per node (a flat
  `{node_id: score}` map, ~74k entries). Also not tabular for the same reason.
- **`complexity.json`** — per-Act structural complexity metrics (citation
  density, defined-term density, indeterminate-concept frequency,
  conditional-statement frequency). One row per Act, viewable in the preview
  above.

See [github.com/cchew/lex-au-graph](https://github.com/cchew/lex-au-graph)
for source code, the MCP server, and version history.

## Licence

CC BY 4.0. Source legislation is Crown copyright - Commonwealth of Australia; reproduction permitted for non-commercial and research purposes under the [PSI Framework](https://www.legislation.gov.au/Help/Copyright). The code that builds this dataset is MIT-licensed.
