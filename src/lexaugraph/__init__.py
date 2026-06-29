"""lex-au-graph: Cross-reference knowledge graph over Australian legislation."""

__version__ = "0.4.0"

from .graph import LexAuGraph
from .loader import load_corpus, parse_act
from .models import ActData, ActNode, DefinedTermNode, DefinitionResult, RefEdge, SectionNode
from .resolver import DefinitionResolver

__all__ = [
    "LexAuGraph",
    "DefinitionResolver",
    "load_corpus",
    "parse_act",
    "ActData",
    "ActNode",
    "DefinedTermNode",
    "DefinitionResult",
    "RefEdge",
    "SectionNode",
]
