"""Phase 7 Streamlit UI helper tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from chem_workflow.ui_support import (
    optional_text,
    parse_material_lines,
    split_nonempty_lines,
    write_uploaded_file,
    zip_directory_to_bytes,
)


@dataclass(frozen=True)
class FakeUpload:
    name: str
    payload: bytes

    def getvalue(self) -> bytes:
        return self.payload


def test_optional_text_normalizes_blanks() -> None:
    assert optional_text("  CDCl3 ") == "CDCl3"
    assert optional_text("   ") is None
    assert optional_text(None) is None


def test_split_nonempty_lines_strips_empty_lines() -> None:
    assert split_nonempty_lines(" A \n\n B\n") == ["A", "B"]


def test_parse_material_lines_accepts_pipe_comma_and_name_only() -> None:
    materials = parse_material_lines(
        """
        benzoic acid | 1.0 mmol
        ethanol, 5 mL
        catalyst
        """
    )

    assert [material.name for material in materials] == [
        "benzoic acid",
        "ethanol",
        "catalyst",
    ]
    assert [material.amount for material in materials] == ["1.0 mmol", "5 mL", None]


def test_write_uploaded_file_uses_basename(tmp_path: Path) -> None:
    path = write_uploaded_file(FakeUpload("../example.mol", b"mol data"), tmp_path)

    assert path == tmp_path / "example.mol"
    assert path.read_bytes() == b"mol data"


def test_zip_directory_to_bytes_includes_directory_root(tmp_path: Path) -> None:
    project = tmp_path / "C001"
    nested = project / "reports"
    nested.mkdir(parents=True)
    (nested / "summary.md").write_text("# Compound C001\n", encoding="utf-8")

    archive_bytes = zip_directory_to_bytes(project)
    archive_path = tmp_path / "archive.zip"
    archive_path.write_bytes(archive_bytes)

    with ZipFile(archive_path) as archive:
        assert archive.namelist() == ["C001/reports/summary.md"]
