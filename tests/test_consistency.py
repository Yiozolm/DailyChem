"""Phase 8 signal-count consistency tests."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from chem_workflow.cli import app
from chem_workflow.consistency import (
    ConsistencyError,
    check_signal_count,
    expected_unique_signals,
)
from chem_workflow.nmr import NMRPeak, NMRSpectrum
from chem_workflow.structure import parse_smiles

ETHYL_BENZOATE = "CCOC(=O)c1ccccc1"
P_XYLENE = "Cc1ccc(C)cc1"


def _spectrum(nucleus: str, n: int) -> NMRSpectrum:
    return NMRSpectrum(nucleus=nucleus, peaks=[NMRPeak(shift_ppm=float(i)) for i in range(n)])


def test_expected_unique_13c_signals() -> None:
    assert expected_unique_signals(parse_smiles(ETHYL_BENZOATE), "13C") == 7
    assert expected_unique_signals(parse_smiles(P_XYLENE), "13C") == 3


def test_expected_unique_1h_signals() -> None:
    assert expected_unique_signals(parse_smiles(ETHYL_BENZOATE), "1H") == 5
    assert expected_unique_signals(parse_smiles(P_XYLENE), "1H") == 2


def test_expected_unique_19f_signals() -> None:
    assert expected_unique_signals(parse_smiles("Cc1ccc(F)cc1"), "19F") == 1


def test_check_match() -> None:
    check = check_signal_count(parse_smiles(ETHYL_BENZOATE), _spectrum("13C", 7))
    assert check.verdict == "match"


def test_check_more_observed() -> None:
    check = check_signal_count(parse_smiles(ETHYL_BENZOATE), _spectrum("13C", 9))
    assert check.verdict == "more_observed"
    assert "多于" in check.message


def test_check_fewer_observed() -> None:
    check = check_signal_count(parse_smiles(ETHYL_BENZOATE), _spectrum("13C", 5))
    assert check.verdict == "fewer_observed"
    assert "少于" in check.message


def test_expected_unique_signals_unsupported_nucleus() -> None:
    with pytest.raises(ConsistencyError):
        expected_unique_signals(parse_smiles(ETHYL_BENZOATE), "11B")


def test_check_empty_spectrum_raises() -> None:
    with pytest.raises(ConsistencyError):
        check_signal_count(parse_smiles(ETHYL_BENZOATE), NMRSpectrum(nucleus="13C", peaks=[]))


def test_cli_nmr_check_match() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "nmr",
            "check",
            "--nucleus",
            "13C",
            "--smiles",
            ETHYL_BENZOATE,
            "--inline",
            "166.7, 132.8, 130.5, 129.6, 128.4, 60.9, 14.4",
        ],
    )

    assert result.exit_code == 0
    assert "一致" in result.output


def test_cli_nmr_check_mismatch() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "nmr",
            "check",
            "--nucleus",
            "13C",
            "--smiles",
            ETHYL_BENZOATE,
            "--inline",
            "166.7, 60.9, 14.4",
        ],
    )

    assert result.exit_code == 0
    assert "少于" in result.output
