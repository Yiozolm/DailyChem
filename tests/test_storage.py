"""Phase 6 local compound archive tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from chem_workflow.cli import app
from chem_workflow.storage import (
    RawFileGroup,
    StorageError,
    init_compound_archive,
)


def test_init_compound_archive_creates_standard_structure(tmp_path: Path) -> None:
    result = init_compound_archive(
        compound_id="C001",
        project_dir=tmp_path,
        smiles="CCO",
    )

    compound_dir = tmp_path / "compounds" / "C001"
    assert result.compound_dir == compound_dir
    assert (compound_dir / "metadata.json").exists()
    assert (compound_dir / "structure" / "structure.smi").exists()
    assert (compound_dir / "structure" / "structure.mol").exists()
    assert (compound_dir / "structure" / "structure_indexed.svg").exists()
    assert (compound_dir / "nmr" / "1H" / "raw").is_dir()
    assert (compound_dir / "nmr" / "13C" / "raw").is_dir()
    assert (compound_dir / "ms" / "raw").is_dir()
    assert (compound_dir / "ir" / "raw").is_dir()
    assert (compound_dir / "records").is_dir()
    assert (compound_dir / "reports" / "summary.md").exists()

    metadata = json.loads((compound_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["compound_id"] == "C001"
    assert metadata["smiles"] == "CCO"
    assert metadata["formula"] == "C2H6O"
    assert metadata["molecular_weight"] == pytest.approx(46.069)
    assert metadata["created_at"]


def test_init_compound_archive_copies_raw_files(tmp_path: Path) -> None:
    raw_nmr = tmp_path / "raw_h.tsv"
    raw_ms = tmp_path / "hrms.txt"
    raw_nmr.write_text("Name\tShift\nA\t7.26\n", encoding="utf-8")
    raw_ms.write_text("found 173.0570\n", encoding="utf-8")

    result = init_compound_archive(
        compound_id="C002",
        project_dir=tmp_path / "project",
        smiles="c1ccccc1",
        raw_file_groups=(
            RawFileGroup("1H NMR", Path("nmr/1H/raw"), (raw_nmr,)),
            RawFileGroup("MS", Path("ms/raw"), (raw_ms,)),
        ),
    )

    copied_relatives = {
        str(path.relative_to(result.compound_dir)) for path in result.copied_raw_files
    }
    assert copied_relatives == {"nmr/1H/raw/raw_h.tsv", "ms/raw/hrms.txt"}

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["copied_raw_files"] == ["nmr/1H/raw/raw_h.tsv", "ms/raw/hrms.txt"]
    summary = result.summary_path.read_text(encoding="utf-8")
    assert "nmr/1H/raw/raw_h.tsv" in summary
    assert "ms/raw/hrms.txt" in summary


def test_init_compound_archive_rejects_duplicate_without_overwrite(tmp_path: Path) -> None:
    init_compound_archive(compound_id="C003", project_dir=tmp_path, smiles="CCO")

    with pytest.raises(StorageError, match="已存在"):
        init_compound_archive(compound_id="C003", project_dir=tmp_path, smiles="CCO")


def test_init_compound_archive_allows_overwrite(tmp_path: Path) -> None:
    first = init_compound_archive(compound_id="C004", project_dir=tmp_path, smiles="CCO")
    marker = first.compound_dir / "reports" / "summary.md"
    marker.write_text("stale", encoding="utf-8")

    second = init_compound_archive(
        compound_id="C004",
        project_dir=tmp_path,
        smiles="CCN",
        overwrite=True,
    )

    metadata = json.loads(second.metadata_path.read_text(encoding="utf-8"))
    assert metadata["smiles"] == "CCN"
    assert "stale" not in marker.read_text(encoding="utf-8")


def test_init_compound_archive_requires_exactly_one_structure_input(tmp_path: Path) -> None:
    with pytest.raises(StorageError, match="二者之一"):
        init_compound_archive(compound_id="C005", project_dir=tmp_path)

    with pytest.raises(StorageError, match="二者之一"):
        init_compound_archive(
            compound_id="C005",
            project_dir=tmp_path,
            smiles="CCO",
            structure_path=tmp_path / "dummy.smi",
        )


def test_init_compound_archive_rejects_unsafe_compound_id(tmp_path: Path) -> None:
    with pytest.raises(StorageError, match="路径分隔符"):
        init_compound_archive(compound_id="../C006", project_dir=tmp_path, smiles="CCO")


def test_cli_init_compound_creates_project(tmp_path: Path) -> None:
    runner = CliRunner()
    project_dir = tmp_path / "demo"

    result = runner.invoke(
        app,
        [
            "init-compound",
            "--id",
            "C007",
            "--project-dir",
            str(project_dir),
            "--smiles",
            "CCO",
        ],
    )

    assert result.exit_code == 0
    assert "已初始化" in result.output
    assert (project_dir / "compounds" / "C007" / "metadata.json").exists()


def test_cli_init_compound_copies_raw_file(tmp_path: Path) -> None:
    runner = CliRunner()
    project_dir = tmp_path / "demo"
    raw_file = tmp_path / "h1.tsv"
    raw_file.write_text("Name\tShift\nA\t7.26\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "init-compound",
            "--id",
            "C008",
            "--project-dir",
            str(project_dir),
            "--smiles",
            "CCO",
            "--copy-nmr-1h",
            str(raw_file),
        ],
    )

    assert result.exit_code == 0
    assert "copied:   1 file(s)" in result.output
    assert (project_dir / "compounds" / "C008" / "nmr" / "1H" / "raw" / "h1.tsv").exists()
