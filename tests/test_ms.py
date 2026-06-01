"""Phase 10 MS / HRMS tests."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from chem_workflow.cli import app
from chem_workflow.ms import (
    MSInputError,
    available_adducts,
    compute_hrms,
    format_hrms,
    hrms_from_manual,
    ppm_error,
)

ETHYL_BENZOATE = "CCOC(=O)c1ccccc1"


def test_compute_hrms_sodium_adduct_matches_reference() -> None:
    result = compute_hrms(smiles=ETHYL_BENZOATE, adduct="[M+Na]+", found_mz=173.0570)

    assert result.ion_formula == "C9H10O2Na"
    assert round(result.calculated_mz, 4) == 173.0573
    assert result.adduct == "[M + Na]+"
    assert result.ppm_error == -1.7


def test_compute_hrms_proton_adduct_formula_and_mass() -> None:
    result = compute_hrms(smiles=ETHYL_BENZOATE, adduct="[M+H]+")

    assert result.ion_formula == "C9H11O2"
    assert round(result.calculated_mz, 4) == 151.0754
    assert result.found_mz is None
    assert result.ppm_error is None


def test_compute_hrms_negative_adduct() -> None:
    result = compute_hrms(smiles="CC(=O)O", adduct="[M-H]-")

    assert result.ion_formula == "C2H3O2"
    assert result.adduct == "[M - H]-"
    assert round(result.calculated_mz, 4) == 59.0139


def test_compute_hrms_ammonium_adduct_adds_n_and_h() -> None:
    result = compute_hrms(smiles=ETHYL_BENZOATE, adduct="[M+NH4]+")

    assert result.ion_formula == "C9H14NO2"


def test_hrms_from_manual_only_computes_ppm() -> None:
    result = hrms_from_manual(
        ion_formula="C9H10O2Na",
        calculated_mz=173.0573,
        adduct="[M+Na]+",
        found_mz=173.0570,
    )

    assert result.ion_formula == "C9H10O2Na"
    assert result.ppm_error == -1.7


def test_format_hrms_full_line() -> None:
    result = compute_hrms(smiles=ETHYL_BENZOATE, adduct="[M+Na]+", found_mz=173.0570)

    line = format_hrms(result)

    assert line == (
        "HRMS (ESI) m/z calculated for C9H10O2Na [M + Na]+ 173.0573, "
        "found 173.0570 (ppm error -1.7)."
    )


def test_ppm_error_sign() -> None:
    assert ppm_error(100.0, 100.001) == 10.0
    assert ppm_error(100.0, 99.999) == -10.0


def test_unknown_adduct_raises() -> None:
    with pytest.raises(MSInputError, match="暂不支持 adduct"):
        compute_hrms(smiles=ETHYL_BENZOATE, adduct="[M+Cs]+")


def test_invalid_smiles_raises_ms_input_error() -> None:
    with pytest.raises(MSInputError):
        compute_hrms(smiles="not-a-smiles", adduct="[M+H]+")


def test_smiles_and_structure_are_mutually_exclusive() -> None:
    with pytest.raises(MSInputError, match="二选一"):
        compute_hrms(smiles=ETHYL_BENZOATE, structure_path="x.mol", adduct="[M+H]+")


def test_available_adducts_includes_common_set() -> None:
    adducts = available_adducts()

    assert "[M+Na]+" in adducts
    assert "[M-H]-" in adducts


def test_cli_ms_hrms_auto() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["ms", "hrms", "--smiles", ETHYL_BENZOATE, "--adduct", "[M+Na]+", "--found", "173.0570"],
    )

    assert result.exit_code == 0
    assert "C9H10O2Na [M + Na]+ 173.0573" in result.output
    assert "ppm error -1.7" in result.output


def test_cli_ms_hrms_manual() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["ms", "hrms", "--ion-formula", "C9H10O2Na", "--calc", "173.0573", "--found", "173.0570"],
    )

    assert result.exit_code == 0
    assert "found 173.0570" in result.output


def test_cli_ms_hrms_unknown_adduct_exits_nonzero() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["ms", "hrms", "--smiles", ETHYL_BENZOATE, "--adduct", "[M+Cs]+"])

    assert result.exit_code == 1
    assert "暂不支持" in result.output
