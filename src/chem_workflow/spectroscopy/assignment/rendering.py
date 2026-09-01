"""Render assignment drafts and editable review rows."""

from __future__ import annotations

from chem_workflow.spectroscopy.assignment.models import (
    AssignmentCandidate,
    AssignmentDraft,
    AssignmentWarning,
    DetectedFeature,
    PeakAssignment,
)
from chem_workflow.spectroscopy.nmr.models import NMRPeak


def render_assignment_draft(draft: AssignmentDraft) -> str:
    """Render an assignment draft as Markdown."""
    proton_line = (
        f"- Expected proton count from structure: {draft.expected_protons}"
        if draft.nucleus == "1H"
        else f"- Formula proton count: {draft.expected_protons}"
    )
    lines: list[str] = [
        f"# {draft.nucleus} NMR Assignment Draft",
        "",
        "> Candidate assignment only. Manual confirmation is required.",
        "",
        "## Compound",
        "",
        f"- Canonical SMILES: `{draft.compound_smiles}`",
        f"- Formula: {draft.formula}",
        proton_line,
        "",
        "## Detected structural features",
        "",
    ]
    lines.extend(_render_feature_lines(draft.features))
    lines.extend(["", "## Peak-level candidates", ""])
    lines.extend(_render_assignment_table(draft.peak_assignments))
    lines.extend(["", "## Warnings and review notes", ""])
    lines.extend(_render_warning_lines(draft.warnings))
    lines.extend(["", "## Review status", ""])
    lines.append(
        "All rows start as `candidate` or `needs_review`. Change a row to `confirmed` only after "
        "manual inspection against the structure and original spectrum."
    )
    return "\n".join(lines).rstrip() + "\n"

def assignment_rows_for_review(draft: AssignmentDraft) -> list[dict[str, object]]:
    """Return editable row dictionaries for CLI/UI review tables."""
    rows: list[dict[str, object]] = []
    for assignment in draft.peak_assignments:
        rows.append(
            {
                "peak": _format_peak(assignment.peak),
                "integration": _format_optional_number(assignment.peak.integration),
                "multiplicity": assignment.peak.multiplicity or "",
                "candidates": "; ".join(candidate.label for candidate in assignment.candidates),
                "status": assignment.status,
                "selected_assignment": assignment.selected_label or "",
                "manual_note": assignment.manual_note or "",
            }
        )
    return rows

def _render_feature_lines(features: tuple[DetectedFeature, ...]) -> list[str]:
    if not features:
        return ["- No supported proton features detected."]
    return [
        (
            f"- **{feature.label}** — atoms {list(feature.atom_indices)}"
            f"{_feature_proton_suffix(feature)}"
        )
        for feature in features
    ]

def _feature_proton_suffix(feature: DetectedFeature) -> str:
    if feature.proton_count is None:
        return ""
    return f", expected {feature.proton_count:g}H"

def _render_assignment_table(assignments: tuple[PeakAssignment, ...]) -> list[str]:
    lines = [
        "| Peak | Multiplicity | Integral | Candidate assignments | Status |",
        "|---|---:|---:|---|---|",
    ]
    for assignment in assignments:
        candidates = _format_candidates(assignment.candidates)
        lines.append(
            "| "
            f"{_format_peak(assignment.peak)} | "
            f"{assignment.peak.multiplicity or ''} | "
            f"{_format_optional_number(assignment.peak.integration)} | "
            f"{candidates} | "
            f"{assignment.status} |"
        )
    return lines

def _format_candidates(candidates: tuple[AssignmentCandidate, ...]) -> str:
    if not candidates:
        return "needs review"
    rendered: list[str] = []
    for candidate in candidates[:3]:
        evidence = "; ".join(candidate.evidence)
        rendered.append(f"{candidate.label} ({candidate.confidence:.2f}; {evidence})")
    return "<br>".join(rendered)

def _render_warning_lines(warnings: tuple[AssignmentWarning, ...]) -> list[str]:
    if not warnings:
        return ["- No warnings."]
    return [f"- **{warning.severity} / {warning.code}**: {warning.message}" for warning in warnings]

def _format_peak(peak: NMRPeak) -> str:
    if peak.shift_range is None:
        return f"δ {peak.shift_ppm:.2f}"
    low, high = peak.shift_range
    return f"δ {high:.2f}–{low:.2f}"

def _format_optional_number(value: float | None) -> str:
    if value is None:
        return ""
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")

__all__ = ["assignment_rows_for_review", "render_assignment_draft"]

