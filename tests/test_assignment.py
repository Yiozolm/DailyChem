"""Phase 8 rule-based NMR assignment tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from chem_workflow.assignment import (
    assign_1h_nmr,
    assign_nmr,
    detect_carbon_features,
    detect_proton_features,
    render_assignment_draft,
)
from chem_workflow.cli import app
from chem_workflow.nmr import NMRPeak, NMRSpectrum, parse_mestrenova_multiplet_table
from chem_workflow.structure import parse_smiles


def _spectrum(text: str):
    return parse_mestrenova_multiplet_table(text, nucleus="1H", frequency_mhz=400, solvent="CDCl3")


def test_detect_proton_features_for_common_fragments() -> None:
    anisole = parse_smiles("COc1ccccc1")
    ethyl_benzoate = parse_smiles("CCOC(=O)c1ccccc1")
    tert_butyl_benzene = parse_smiles("CC(C)(C)c1ccccc1")

    anisole_features = {feature.feature_id for feature in detect_proton_features(anisole)}
    ethyl_features = {feature.feature_id for feature in detect_proton_features(ethyl_benzoate)}
    tert_butyl_features = {
        feature.feature_id for feature in detect_proton_features(tert_butyl_benzene)
    }

    assert {"aromatic_H", "OCH3"}.issubset(anisole_features)
    assert {"aromatic_H", "ethyl_CH3", "ethyl_CH2", "OCH2"}.issubset(ethyl_features)
    assert {"aromatic_H", "tert_butyl_CH3", "alkyl_CH3"}.issubset(tert_butyl_features)


def test_assign_1h_nmr_generates_aromatic_and_methoxy_candidates() -> None:
    mol = parse_smiles("COc1ccccc1")
    spectrum = _spectrum("Name\tShift\tH's\tClass\nA\t7.25\t5\tm\nB\t3.80\t3\ts\n")

    draft = assign_1h_nmr(mol, spectrum)

    candidate_labels = [
        candidate.label
        for assignment in draft.peak_assignments
        for candidate in assignment.candidates
    ]
    assert "aromatic H" in candidate_labels
    assert "OCH3" in candidate_labels
    assert {assignment.status for assignment in draft.peak_assignments} == {"candidate"}


def test_assign_1h_nmr_generates_ethyl_and_tert_butyl_candidates() -> None:
    ethyl = parse_smiles("CCOC(=O)c1ccccc1")
    ethyl_spectrum = _spectrum(
        "Name\tShift\tH's\tClass\nA\t7.45\t5\tm\nB\t4.35\t2\tq\nC\t1.35\t3\tt\n"
    )
    ethyl_draft = assign_1h_nmr(ethyl, ethyl_spectrum)

    ethyl_labels = {
        candidate.label
        for assignment in ethyl_draft.peak_assignments
        for candidate in assignment.candidates
    }
    assert {"aromatic H", "ethyl CH2", "ethyl CH3", "OCH2"}.issubset(ethyl_labels)

    tert_butyl = parse_smiles("CC(C)(C)c1ccccc1")
    tert_spectrum = _spectrum("Name\tShift\tH's\tClass\nA\t7.30\t5\tm\nB\t1.31\t9\ts\n")
    tert_draft = assign_1h_nmr(tert_butyl, tert_spectrum)

    tert_labels = {
        candidate.label
        for assignment in tert_draft.peak_assignments
        for candidate in assignment.candidates
    }
    assert "tert-butyl CH3" in tert_labels


def test_assignment_draft_warns_without_overclaiming() -> None:
    mol = parse_smiles("COc1ccccc1")
    spectrum = _spectrum("Name\tShift\tH's\tClass\nA\t11.00\t3\ts\n")

    draft = assign_1h_nmr(mol, spectrum)
    markdown = render_assignment_draft(draft)

    assert draft.peak_assignments[0].status == "needs_review"
    assert "Candidate assignment only" in markdown
    assert "Manual confirmation is required" in markdown
    assert any(warning.code == "integration_total_mismatch" for warning in draft.warnings)


def test_cli_nmr_assign_outputs_markdown() -> None:
    runner = CliRunner()
    inline = "Name\tShift\tH's\tClass\nA\t7.25\t5\tm\nB\t3.80\t3\ts\n"

    result = runner.invoke(
        app,
        [
            "nmr",
            "assign",
            "--inline",
            inline,
            "--smiles",
            "COc1ccccc1",
            "--frequency",
            "400",
            "--solvent",
            "CDCl3",
        ],
    )

    assert result.exit_code == 0
    assert "# 1H NMR Assignment Draft" in result.output
    assert "aromatic H" in result.output
    assert "OCH3" in result.output


def test_cli_nmr_assign_writes_output_file(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "assignment.md"
    inline = "Name\tShift\tH's\tClass\nA\t7.25\t5\tm\nB\t3.80\t3\ts\n"

    result = runner.invoke(
        app,
        ["nmr", "assign", "--inline", inline, "--smiles", "COc1ccccc1", "--out", str(out)],
    )

    assert result.exit_code == 0
    assert result.output == f"已写入 {out}\n"
    assert "Candidate assignment only" in out.read_text(encoding="utf-8")


def _c13_spectrum(shifts: list[float]) -> NMRSpectrum:
    return NMRSpectrum(
        nucleus="13C",
        frequency_mhz=101,
        solvent="CDCl3",
        peaks=[NMRPeak(shift_ppm=s) for s in shifts],
    )


def test_detect_carbon_features_for_ethyl_benzoate() -> None:
    features = detect_carbon_features(parse_smiles("CCOC(=O)c1ccccc1"))
    feature_ids = {f.feature_id for f in features}

    assert "carbonyl_C" in feature_ids
    assert "aromatic_C" in feature_ids
    assert "O_C" in feature_ids
    assert "aliphatic_C" in feature_ids


def test_assign_nmr_13c_candidates() -> None:
    mol = parse_smiles("CCOC(=O)c1ccccc1")
    spectrum = _c13_spectrum([166.7, 132.8, 130.5, 129.6, 128.4, 60.9, 14.4])

    draft = assign_nmr(mol, spectrum)

    assert draft.nucleus == "13C"
    labels = {
        candidate.label
        for assignment in draft.peak_assignments
        for candidate in assignment.candidates
    }
    assert "carbonyl / carboxyl C" in labels
    assert "aromatic C" in labels
    # Signal count matches (7 unique carbons, 7 peaks) -> info-level match warning.
    assert any(w.code == "signal_count_match" for w in draft.warnings)


def test_assign_nmr_13c_flags_extra_peak() -> None:
    mol = parse_smiles("CCOC(=O)c1ccccc1")
    spectrum = _c13_spectrum([166.7, 132.8, 130.5, 129.6, 128.4, 60.9, 14.4, 99.9])

    draft = assign_nmr(mol, spectrum)

    assert any(w.code == "signal_count_mismatch" for w in draft.warnings)


def test_assign_1h_nmr_still_works() -> None:
    mol = parse_smiles("COc1ccccc1")
    spectrum = _spectrum("Name\tShift\tH's\tClass\nA\t7.25\t5\tm\nB\t3.80\t3\ts\n")

    draft = assign_1h_nmr(mol, spectrum)

    assert draft.nucleus == "1H"
    assert draft.peak_assignments


def test_assign_1h_nmr_rejects_non_proton() -> None:
    mol = parse_smiles("CCOC(=O)c1ccccc1")
    with pytest.raises(ValueError, match="1H"):
        assign_1h_nmr(mol, _c13_spectrum([166.7]))


def test_cli_nmr_assign_13c() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "nmr",
            "assign",
            "--nucleus",
            "13C",
            "--smiles",
            "CCOC(=O)c1ccccc1",
            "--inline",
            "166.7, 60.9, 14.4",
        ],
    )

    assert result.exit_code == 0
    assert "13C NMR Assignment Draft" in result.output
