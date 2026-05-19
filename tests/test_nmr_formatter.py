"""Phase 4 NMR text formatter tests."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from chem_workflow.cli import app
from chem_workflow.nmr import NMRPeak, NMRSpectrum, parse_mestrenova_multiplet_table
from chem_workflow.nmr_formatter import (
    NMRFormatError,
    NMRFormatOptions,
    format_nmr_spectrum,
)

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "raw"
MULTIPLET_CLEAN_FIXTURE = FIXTURES / "nmr_multiplet_table_clean_example.tsv"


def test_format_1h_nmr_default_publication_style() -> None:
    spectrum = parse_mestrenova_multiplet_table(
        MULTIPLET_CLEAN_FIXTURE,
        frequency_mhz=400,
        solvent="CDCl3",
    )

    assert format_nmr_spectrum(spectrum) == (
        "1H NMR (400 MHz, CDCl3) δ "
        "8.56 (s, 2H), 7.51 (s, 2H), 5.17 (s, 2H), "
        "3.11 (s, 9H), 2.72 (s, 2H), 1.24 (s, 2H)."
    )


def test_format_1h_nmr_with_j_values() -> None:
    spectrum = NMRSpectrum(
        nucleus="1H",
        frequency_mhz=500,
        solvent="DMSO-d6",
        peaks=[
            NMRPeak(shift_ppm=7.26, multiplicity="dd", integration=1.0, j_hz=[8.0, 2.0]),
        ],
    )

    assert format_nmr_spectrum(spectrum) == (
        "1H NMR (500 MHz, DMSO-d6) δ 7.26 (dd, J = 8.0, 2.0 Hz, 1H)."
    )


def test_format_1h_nmr_omits_empty_peak_details() -> None:
    spectrum = NMRSpectrum(nucleus="1H", peaks=[NMRPeak(shift_ppm=7.26)])

    assert format_nmr_spectrum(spectrum) == "1H NMR δ 7.26."


def test_format_1h_nmr_include_assignment_when_requested() -> None:
    spectrum = NMRSpectrum(
        nucleus="1H",
        peaks=[NMRPeak(shift_ppm=3.85, multiplicity="s", integration=3.0, assignment="OCH3")],
    )

    assert (
        format_nmr_spectrum(
            spectrum,
            NMRFormatOptions(include_assignment=True),
        )
        == "1H NMR δ 3.85 (s, 3H, assignment OCH3)."
    )


def test_format_1h_nmr_hides_frequency_and_solvent_when_requested() -> None:
    spectrum = NMRSpectrum(
        nucleus="1H",
        frequency_mhz=400,
        solvent="CDCl3",
        peaks=[NMRPeak(shift_ppm=1.24, multiplicity="s", integration=2.0)],
    )

    assert (
        format_nmr_spectrum(
            spectrum,
            NMRFormatOptions(include_frequency=False, include_solvent=False),
        )
        == "1H NMR δ 1.24 (s, 2H)."
    )


def test_format_nmr_header_supports_only_solvent() -> None:
    spectrum = NMRSpectrum(
        nucleus="1H",
        solvent="CDCl3",
        peaks=[NMRPeak(shift_ppm=1.24, multiplicity="s", integration=2.0)],
    )

    assert format_nmr_spectrum(spectrum) == "1H NMR (CDCl3) δ 1.24 (s, 2H)."


def test_format_nmr_preserve_order_option() -> None:
    spectrum = NMRSpectrum(
        nucleus="1H",
        peaks=[
            NMRPeak(shift_ppm=1.00, multiplicity="s", integration=3.0),
            NMRPeak(shift_ppm=9.00, multiplicity="s", integration=1.0),
        ],
    )

    assert (
        format_nmr_spectrum(
            spectrum,
            NMRFormatOptions(sort_descending=False),
        )
        == "1H NMR δ 1.00 (s, 3H), 9.00 (s, 1H)."
    )


def test_format_13c_nmr_default_style() -> None:
    spectrum = NMRSpectrum(
        nucleus="13C",
        frequency_mhz=101,
        solvent="CDCl3",
        peaks=[
            NMRPeak(shift_ppm=52.12),
            NMRPeak(shift_ppm=165.24),
            NMRPeak(shift_ppm=129.49),
        ],
    )

    assert format_nmr_spectrum(spectrum) == ("13C NMR (101 MHz, CDCl3) δ 165.2, 129.5, 52.1.")


def test_format_13c_nmr_include_assignment_when_requested() -> None:
    spectrum = NMRSpectrum(
        nucleus="13C",
        peaks=[NMRPeak(shift_ppm=165.24, assignment="C=O")],
    )

    assert (
        format_nmr_spectrum(
            spectrum,
            NMRFormatOptions(include_assignment=True),
        )
        == "13C NMR δ 165.2 (C=O)."
    )


def test_format_non_integer_frequency() -> None:
    spectrum = NMRSpectrum(
        nucleus="13C",
        frequency_mhz=100.62,
        solvent="CDCl3",
        peaks=[NMRPeak(shift_ppm=165.24)],
    )

    assert format_nmr_spectrum(spectrum) == "13C NMR (100.62 MHz, CDCl3) δ 165.2."


def test_format_empty_spectrum_raises() -> None:
    spectrum = NMRSpectrum(nucleus="1H", peaks=[])

    with pytest.raises(NMRFormatError, match="without peaks"):
        format_nmr_spectrum(spectrum)


def test_format_unsupported_nucleus_raises() -> None:
    spectrum = NMRSpectrum(nucleus="19F", peaks=[NMRPeak(shift_ppm=-63.5)])

    with pytest.raises(NMRFormatError, match="not implemented"):
        format_nmr_spectrum(spectrum)


def test_cli_nmr_format_outputs_text() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "nmr",
            "format",
            str(MULTIPLET_CLEAN_FIXTURE),
            "--frequency",
            "400",
            "--solvent",
            "CDCl3",
        ],
    )

    assert result.exit_code == 0
    assert result.output == (
        "1H NMR (400 MHz, CDCl3) δ "
        "8.56 (s, 2H), 7.51 (s, 2H), 5.17 (s, 2H), "
        "3.11 (s, 9H), 2.72 (s, 2H), 1.24 (s, 2H).\n"
    )


def test_cli_nmr_format_writes_output_file(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "nmr_report.txt"

    result = runner.invoke(
        app,
        [
            "nmr",
            "format",
            str(MULTIPLET_CLEAN_FIXTURE),
            "--frequency",
            "400",
            "--solvent",
            "CDCl3",
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0
    assert result.output == f"已写入 {out}\n"
    assert out.read_text(encoding="utf-8") == (
        "1H NMR (400 MHz, CDCl3) δ "
        "8.56 (s, 2H), 7.51 (s, 2H), 5.17 (s, 2H), "
        "3.11 (s, 9H), 2.72 (s, 2H), 1.24 (s, 2H).\n"
    )
