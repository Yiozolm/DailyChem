"""Phase 10 IR formatter tests."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from chem_workflow.cli import app
from chem_workflow.ir import IRInputError, format_ir, parse_ir_peaks


def test_parse_ir_peaks_comma_separated() -> None:
    spectrum = parse_ir_peaks("3050, 2920, 1715, 1600, 1450")

    assert [band.wavenumber for band in spectrum.bands] == [3050, 2920, 1715, 1600, 1450]
    assert spectrum.technique == "neat"


def test_parse_ir_peaks_with_intensity() -> None:
    spectrum = parse_ir_peaks("1715 (s), 2920 m, 3050 w")

    by_wavenumber = {band.wavenumber: band.intensity for band in spectrum.bands}
    assert by_wavenumber[1715] == "s"
    assert by_wavenumber[2920] == "m"
    assert by_wavenumber[3050] == "w"


def test_format_ir_sorts_descending() -> None:
    spectrum = parse_ir_peaks("1450, 3050, 1715")

    line = format_ir(spectrum)

    assert line == "IR (neat) νmax 3050, 1715, 1450 cm⁻¹."


def test_format_ir_preserve_order_and_intensity() -> None:
    spectrum = parse_ir_peaks("1715 s, 2920 m")

    line = format_ir(spectrum, sort_descending=False, include_intensity=True)

    assert line == "IR (neat) νmax 1715 (s), 2920 (m) cm⁻¹."


def test_format_ir_custom_technique() -> None:
    spectrum = parse_ir_peaks("1715", technique="KBr")

    assert format_ir(spectrum) == "IR (KBr) νmax 1715 cm⁻¹."


def test_parse_ir_empty_raises() -> None:
    with pytest.raises(IRInputError, match="为空"):
        parse_ir_peaks("   ")


def test_parse_ir_no_numbers_raises() -> None:
    with pytest.raises(IRInputError, match="未能"):
        parse_ir_peaks("strong, medium")


def test_cli_ir_format_inline() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["ir", "format", "--inline", "3050, 2920, 1715"])

    assert result.exit_code == 0
    assert result.output.strip() == "IR (neat) νmax 3050, 2920, 1715 cm⁻¹."


def test_cli_ir_format_empty_exits_nonzero() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["ir", "format", "--inline", "   "])

    assert result.exit_code == 1
