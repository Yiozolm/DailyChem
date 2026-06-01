"""Phase 10 UV-vis formatter tests."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from chem_workflow.cli import app
from chem_workflow.uv import UVInputError, format_uv, parse_uv_peaks


def test_parse_uv_single_lambda() -> None:
    spectrum = parse_uv_peaks("254", solvent="MeOH")

    assert [band.lambda_max for band in spectrum.bands] == [254]
    assert spectrum.solvent == "MeOH"


def test_parse_uv_with_epsilon() -> None:
    spectrum = parse_uv_peaks("254 (12000), 320 4500")

    by_lambda = {band.lambda_max: band.epsilon for band in spectrum.bands}
    assert by_lambda[254] == 12000
    assert by_lambda[320] == 4500


def test_format_uv_basic() -> None:
    spectrum = parse_uv_peaks("254", solvent="MeOH")

    assert format_uv(spectrum) == "UV-vis (MeOH) λmax 254 nm."


def test_format_uv_sorts_ascending_with_epsilon() -> None:
    spectrum = parse_uv_peaks("320 4500, 254 12000", solvent="MeOH")

    line = format_uv(spectrum)

    assert line == "UV-vis (MeOH) λmax 254 nm (ε 12000), 320 nm (ε 4500)."


def test_format_uv_without_solvent() -> None:
    spectrum = parse_uv_peaks("254")

    assert format_uv(spectrum) == "UV-vis λmax 254 nm."


def test_parse_uv_empty_raises() -> None:
    with pytest.raises(UVInputError, match="为空"):
        parse_uv_peaks("  ")


def test_cli_uv_format_inline() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["uv", "format", "--inline", "254", "--solvent", "MeOH"])

    assert result.exit_code == 0
    assert result.output.strip() == "UV-vis (MeOH) λmax 254 nm."


def test_cli_uv_format_empty_exits_nonzero() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["uv", "format", "--inline", "  "])

    assert result.exit_code == 1
