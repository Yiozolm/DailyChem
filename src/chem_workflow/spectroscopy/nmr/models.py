"""Validated NMR spectrum data models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NMRInputError(ValueError):
    """NMR 输入解析失败时抛出。错误信息会展示给用户，应包含可操作建议。"""


class NMRPeak(BaseModel):
    """One normalized multiplet or shift-list entry."""

    shift_ppm: float
    shift_range: tuple[float, float] | None = None
    integration: float | None = None
    multiplicity: str | None = None
    j_hz: list[float] = Field(default_factory=list)
    assignment: str | None = None
    note: str | None = None


class NMRSpectrum(BaseModel):
    """A nucleus, acquisition metadata, and its normalized peaks."""

    nucleus: Literal["1H", "13C", "19F", "31P"] = "1H"
    frequency_mhz: float | None = None
    solvent: str | None = None
    sample_id: str | None = None
    peaks: list[NMRPeak]


__all__ = ["NMRInputError", "NMRPeak", "NMRSpectrum"]
