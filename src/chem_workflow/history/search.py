"""Phase 11 structure search over the local history database and literature table.

Substructure and similarity (Morgan fingerprint + Tanimoto) search across any records that expose a
``.smiles`` attribute (compounds or literature entries). Records with unparseable SMILES are
skipped so a single bad row does not break a whole search.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator

_MORGAN_GENERATOR = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


class HasSmiles(Protocol):
    smiles: str


RecordT = TypeVar("RecordT", bound=HasSmiles)


class SearchError(ValueError):
    """检索查询非法时抛出。错误信息会展示给用户，应包含可操作建议。"""


@dataclass(frozen=True)
class SearchHit(Generic[RecordT]):
    """A single search result; ``score`` is the Tanimoto similarity, or None for substructure."""

    record: RecordT
    score: float | None = None

    @property
    def compound(self) -> RecordT:
        """Backwards-compatible alias for ``record``."""
        return self.record


def substructure_search(records: list[RecordT], query: str) -> list[SearchHit[RecordT]]:
    """Return records whose structure contains the query substructure (SMARTS or SMILES)."""
    pattern = _parse_query_pattern(query)
    hits: list[SearchHit[RecordT]] = []
    for record in records:
        mol = Chem.MolFromSmiles(record.smiles)
        if mol is None:
            continue
        if mol.HasSubstructMatch(pattern):
            hits.append(SearchHit(record=record))
    return hits


def similarity_search(
    records: list[RecordT],
    query_smiles: str,
    *,
    threshold: float = 0.7,
    top_k: int = 10,
) -> list[SearchHit[RecordT]]:
    """Return records with Tanimoto similarity >= threshold, sorted high-to-low (top_k)."""
    if not 0.0 <= threshold <= 1.0:
        raise SearchError("threshold 必须在 0 与 1 之间。")
    query_mol = Chem.MolFromSmiles(query_smiles.strip()) if query_smiles.strip() else None
    if query_mol is None:
        raise SearchError(f"非法查询 SMILES：{query_smiles!r}")

    query_fp = _MORGAN_GENERATOR.GetFingerprint(query_mol)
    scored: list[SearchHit[RecordT]] = []
    for record in records:
        mol = Chem.MolFromSmiles(record.smiles)
        if mol is None:
            continue
        score = DataStructs.TanimotoSimilarity(query_fp, _MORGAN_GENERATOR.GetFingerprint(mol))
        if score >= threshold:
            scored.append(SearchHit(record=record, score=round(score, 4)))

    scored.sort(key=lambda hit: hit.score or 0.0, reverse=True)
    if top_k > 0:
        return scored[:top_k]
    return scored


def _parse_query_pattern(query: str) -> Chem.Mol:
    cleaned = query.strip()
    if not cleaned:
        raise SearchError("查询为空；请提供 SMARTS 或 SMILES。")
    pattern = Chem.MolFromSmarts(cleaned)
    if pattern is None:
        pattern = Chem.MolFromSmiles(cleaned)
    if pattern is None:
        raise SearchError(f"无法解析查询子结构（SMARTS/SMILES）：{query!r}")
    return pattern
