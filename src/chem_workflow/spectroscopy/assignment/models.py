"""Data models for rule-based NMR assignment drafts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from chem_workflow.spectroscopy.nmr.models import NMRPeak

AssignmentStatus = Literal["candidate", "needs_review", "confirmed"]
WarningSeverity = Literal["info", "warning", "risk"]

class AssignmentError(ValueError):
    """Raised when rule loading or assignment drafting fails."""

@dataclass(frozen=True)
class AssignmentRule:
    """A simple 1H NMR shift rule."""

    rule_id: str
    label: str
    shift_range: tuple[float, float]
    description: str
    required_features: tuple[str, ...] = ()
    multiplicities: tuple[str, ...] = ()
    expected_integrations: tuple[float, ...] = ()
    warn_if_missing: bool = True

@dataclass(frozen=True)
class DetectedFeature:
    """A structural feature detected from an RDKit molecule."""

    feature_id: str
    label: str
    description: str
    atom_indices: tuple[int, ...]
    proton_count: float | None = None
    caution: str | None = None

@dataclass(frozen=True)
class AssignmentCandidate:
    """A possible assignment for a peak."""

    rule_id: str
    label: str
    description: str
    confidence: float
    evidence: tuple[str, ...]

@dataclass(frozen=True)
class PeakAssignment:
    """Assignment draft state for one peak."""

    peak: NMRPeak
    candidates: tuple[AssignmentCandidate, ...]
    status: AssignmentStatus
    selected_label: str | None = None
    manual_note: str | None = None

@dataclass(frozen=True)
class AssignmentWarning:
    """Risk or caution emitted by the assignment assistant."""

    code: str
    message: str
    severity: WarningSeverity = "warning"

@dataclass(frozen=True)
class AssignmentDraft:
    """Rule-based assignment draft for an NMR spectrum."""

    compound_smiles: str
    formula: str
    expected_protons: int
    features: tuple[DetectedFeature, ...]
    peak_assignments: tuple[PeakAssignment, ...]
    warnings: tuple[AssignmentWarning, ...]
    nucleus: str = "1H"
    note: str = field(
        default=(
            "Rule-based candidate assignment only. Manual confirmation is required before use in "
            "a report, thesis, paper, or supporting information."
        )
    )

__all__ = [
    "AssignmentCandidate",
    "AssignmentDraft",
    "AssignmentError",
    "AssignmentRule",
    "AssignmentStatus",
    "AssignmentWarning",
    "DetectedFeature",
    "PeakAssignment",
    "WarningSeverity",
]

