"""Compatibility exports for :mod:`chem_workflow.history.search`."""

from chem_workflow.history.search import (
    HasSmiles,
    SearchError,
    SearchHit,
    similarity_search,
    substructure_search,
)

__all__ = [
    "HasSmiles",
    "SearchError",
    "SearchHit",
    "similarity_search",
    "substructure_search",
]
