"""Import standardized compound archives into history records."""

from __future__ import annotations

import json
from pathlib import Path

from chem_workflow.history.models import CompoundRecord, DatabaseError


def record_from_metadata(metadata_path: str | Path) -> CompoundRecord:
    """Build a record from a ``compounds/<id>/metadata.json`` file."""
    path = Path(metadata_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise DatabaseError(f"无法读取 metadata：{path}（{e}）") from e

    compound_id = str(data.get("compound_id") or "").strip()
    smiles = str(data.get("smiles") or "").strip()
    if not compound_id or not smiles:
        raise DatabaseError(f"metadata 缺少 compound_id 或 smiles：{path}")

    compound_dir = path.parent
    return CompoundRecord(
        compound_id=compound_id,
        smiles=smiles,
        formula=_optional_str(data.get("formula")),
        molecular_weight=_optional_float(data.get("molecular_weight")),
        source_dir=str(compound_dir),
        created_at=_optional_str(data.get("created_at")),
        spectra=_collect_spectra_texts(compound_dir),
    )


def scan_archive(project_dir: str | Path = Path(".")) -> list[CompoundRecord]:
    """Find all ``compounds/*/metadata.json`` under ``project_dir``."""
    root = Path(project_dir) / "compounds"
    if not root.exists():
        return []
    return [record_from_metadata(path) for path in sorted(root.glob("*/metadata.json"))]


def _collect_spectra_texts(compound_dir: Path) -> dict[str, str]:
    spectra: dict[str, str] = {}
    candidates = {
        "1H": ("nmr/1H/formatted.txt", "nmr/1H/1H_nmr.txt"),
        "13C": ("nmr/13C/formatted.txt", "nmr/13C/13C_nmr.txt"),
        "HRMS": ("ms/hrms.txt", "ms/hrms_report.txt"),
        "IR": ("ir/ir.txt", "ir/ir_report.txt"),
        "UV": ("uv/uv.txt", "uv/uv_report.txt"),
    }
    for kind, rel_paths in candidates.items():
        for relative in rel_paths:
            path = compound_dir / relative
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    spectra[kind] = text
                    break
    return spectra


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


__all__ = ["record_from_metadata", "scan_archive"]
