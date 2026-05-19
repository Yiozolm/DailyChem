"""Phase 8 rule-based NMR assignment tests."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from chem_workflow.assignment import (
    assign_1h_nmr,
    detect_proton_features,
    render_assignment_draft,
)
from chem_workflow.cli import app
from chem_workflow.nmr import parse_mestrenova_multiplet_table
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
