"""Phase 12 configuration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from chem_workflow.cli import app
from chem_workflow.config import (
    CONFIG_FILENAME,
    ChemwfConfig,
    ConfigError,
    find_config_path,
    load_config,
)


def test_defaults_when_no_file(tmp_path: Path) -> None:
    config = load_config(None)
    # Loading the nearest config from a clean temp dir would still find none.
    assert isinstance(config, ChemwfConfig)
    assert ChemwfConfig().default_solvent == "CDCl3"
    assert ChemwfConfig().default_adduct == "[M+Na]+"


def test_load_from_explicit_file(tmp_path: Path) -> None:
    cfg = tmp_path / CONFIG_FILENAME
    cfg.write_text(
        'default_solvent = "DMSO-d6"\ndefault_frequency_1h = 500.0\n', encoding="utf-8"
    )

    config = load_config(cfg)

    assert config.default_solvent == "DMSO-d6"
    assert config.default_frequency_1h == 500.0
    # Unset keys fall back to defaults.
    assert config.default_adduct == "[M+Na]+"


def test_invalid_field_raises_config_error(tmp_path: Path) -> None:
    cfg = tmp_path / CONFIG_FILENAME
    cfg.write_text('default_frequency_1h = "not-a-number"\n', encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(cfg)


def test_malformed_toml_raises_config_error(tmp_path: Path) -> None:
    cfg = tmp_path / CONFIG_FILENAME
    cfg.write_text("this is = = not toml", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(cfg)


def test_find_config_path_walks_up(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILENAME).write_text("default_solvent = \"C6D6\"\n", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    found = find_config_path(nested)

    assert found == tmp_path / CONFIG_FILENAME


def test_cli_config_init_and_show(tmp_path: Path) -> None:
    runner = CliRunner()

    init = runner.invoke(app, ["config", "init", "--project-dir", str(tmp_path)])
    assert init.exit_code == 0
    assert (tmp_path / CONFIG_FILENAME).exists()

    show = runner.invoke(app, ["config", "show", "--path", str(tmp_path / CONFIG_FILENAME)])
    assert show.exit_code == 0
    assert "default_solvent" in show.output


def test_cli_config_init_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    (tmp_path / CONFIG_FILENAME).write_text("default_solvent = \"CDCl3\"\n", encoding="utf-8")

    result = runner.invoke(app, ["config", "init", "--project-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "已存在" in result.output
