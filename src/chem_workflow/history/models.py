"""Validated local-history and literature records."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DatabaseError(ValueError):
    """本地历史数据库读写失败时抛出。错误信息会展示给用户，应包含可操作建议。"""


class CompoundRecord(BaseModel):
    """A compound plus its characterization texts in the history database."""

    compound_id: str
    smiles: str
    formula: str | None = None
    molecular_weight: float | None = None
    source_dir: str | None = None
    created_at: str | None = None
    spectra: dict[str, str] = Field(default_factory=dict)


class LiteratureRecord(BaseModel):
    """A literature reference plus reported NMR data, keyed by DOI."""

    doi: str
    smiles: str
    title: str | None = None
    authors: str | None = None
    year: int | None = None
    nmr_1h: str | None = None
    nmr_13c: str | None = None
    note: str | None = None


__all__ = ["CompoundRecord", "DatabaseError", "LiteratureRecord"]
