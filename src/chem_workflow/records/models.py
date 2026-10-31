"""Validated experiment-record input models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RecordInputError(ValueError):
    """Raised when an experiment record input file cannot be loaded or validated."""


class Material(BaseModel):
    """A reaction material, reagent, or additive."""

    name: str
    amount: str | None = None


class ReactionInfo(BaseModel):
    """Core reaction conditions used to draft the procedure paragraph."""

    starting_materials: list[Material] = Field(default_factory=list)
    reagents: list[Material] = Field(default_factory=list)
    # Verbatim reaction setup/addition notes from a record or OCR draft.
    procedure: str | None = None
    solvent: str | None = None
    temperature: str | None = None
    time: str | None = None


class YieldInfo(BaseModel):
    """Isolated product yield."""

    mass: str | None = None
    percent: str | None = None


class Characterization(BaseModel):
    """Curated characterization text blocks inserted without inventing data."""

    h1_nmr: str | None = None
    c13_nmr: str | None = None
    hrms: str | None = None
    ms: str | None = None
    ir: str | None = None
    uv: str | None = None
    other: list[str] = Field(default_factory=list)


class ReactionRecord(BaseModel):
    """Structured input for an experiment record draft."""

    model_config = ConfigDict(populate_by_name=True)

    compound_id: str
    product_name: str | None = None
    smiles: str | None = None
    reaction: ReactionInfo = Field(default_factory=ReactionInfo)
    workup: str | None = None
    purification: str | None = None
    appearance: str | None = None
    yield_: YieldInfo | None = Field(default=None, alias="yield")
    characterization: Characterization = Field(default_factory=Characterization)


Language = Literal["en", "zh"]

__all__ = [
    "Characterization",
    "Language",
    "Material",
    "ReactionInfo",
    "ReactionRecord",
    "RecordInputError",
    "YieldInfo",
]
