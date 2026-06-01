"""Phase 11 structure search tests."""

from __future__ import annotations

import pytest

from chem_workflow.database import CompoundRecord, make_record
from chem_workflow.search import SearchError, similarity_search, substructure_search

ETHYL_BENZOATE = "CCOC(=O)c1ccccc1"
METHYL_BENZOATE = "COC(=O)c1ccccc1"
HEXANE = "CCCCCC"


def _records() -> list[CompoundRecord]:
    return [
        make_record(compound_id="C001", smiles=ETHYL_BENZOATE),
        make_record(compound_id="C002", smiles=METHYL_BENZOATE),
        make_record(compound_id="C003", smiles=HEXANE),
    ]


def test_substructure_search_benzene_ring() -> None:
    hits = substructure_search(_records(), "c1ccccc1")

    ids = {hit.compound.compound_id for hit in hits}
    assert ids == {"C001", "C002"}
    assert all(hit.score is None for hit in hits)


def test_substructure_search_ester_smarts() -> None:
    hits = substructure_search(_records(), "C(=O)O")

    ids = {hit.compound.compound_id for hit in hits}
    assert ids == {"C001", "C002"}


def test_similarity_search_ranks_and_filters() -> None:
    hits = similarity_search(_records(), ETHYL_BENZOATE, threshold=0.4)

    assert hits[0].compound.compound_id == "C001"
    assert hits[0].score == 1.0
    # Hexane is well below threshold and must be excluded.
    assert "C003" not in {hit.compound.compound_id for hit in hits}


def test_similarity_search_top_k() -> None:
    hits = similarity_search(_records(), ETHYL_BENZOATE, threshold=0.0, top_k=1)

    assert len(hits) == 1
    assert hits[0].compound.compound_id == "C001"


def test_similarity_search_invalid_query_raises() -> None:
    with pytest.raises(SearchError):
        similarity_search(_records(), "not-a-smiles")


def test_similarity_search_threshold_out_of_range() -> None:
    with pytest.raises(SearchError):
        similarity_search(_records(), ETHYL_BENZOATE, threshold=1.5)


def test_substructure_search_invalid_query_raises() -> None:
    with pytest.raises(SearchError):
        substructure_search(_records(), "[[[")


def test_search_skips_dirty_smiles_rows() -> None:
    records = [
        CompoundRecord(compound_id="bad", smiles="not-a-smiles"),
        make_record(compound_id="C001", smiles=ETHYL_BENZOATE),
    ]

    hits = substructure_search(records, "c1ccccc1")

    assert {hit.compound.compound_id for hit in hits} == {"C001"}
