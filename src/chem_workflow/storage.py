"""Local compound project folder initialization and archiving."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rdkit import Chem

from chem_workflow.structure import draw_structure, load_structure, mol_info, parse_smiles


class StorageError(ValueError):
    """Raised when compound folder initialization or archiving fails."""


@dataclass(frozen=True)
class RawFileGroup:
    """A group of raw files copied into one compound subdirectory."""

    label: str
    destination: Path
    sources: tuple[Path, ...]


@dataclass(frozen=True)
class CompoundArchiveResult:
    """Paths written by `init_compound_archive`."""

    compound_dir: Path
    metadata_path: Path
    summary_path: Path
    structure_files: tuple[Path, ...]
    copied_raw_files: tuple[Path, ...]


@dataclass(frozen=True)
class CompoundMetadata:
    """Serializable compound metadata for `metadata.json`."""

    compound_id: str
    smiles: str
    formula: str
    molecular_weight: float
    heavy_atoms: int
    num_atoms: int
    created_at: str
    structure_source: str
    copied_raw_files: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dictionary."""
        return {
            "compound_id": self.compound_id,
            "smiles": self.smiles,
            "formula": self.formula,
            "molecular_weight": self.molecular_weight,
            "heavy_atoms": self.heavy_atoms,
            "num_atoms": self.num_atoms,
            "created_at": self.created_at,
            "structure_source": self.structure_source,
            "copied_raw_files": list(self.copied_raw_files),
        }


STANDARD_DIRS = (
    "structure",
    "nmr/1H/raw",
    "nmr/13C/raw",
    "ms/raw",
    "ir/raw",
    "records",
    "reports",
)


def init_compound_archive(
    *,
    compound_id: str,
    project_dir: str | Path,
    smiles: str | None = None,
    structure_path: str | Path | None = None,
    raw_file_groups: tuple[RawFileGroup, ...] = (),
    overwrite: bool = False,
) -> CompoundArchiveResult:
    """Create a standardized local archive folder for one compound.

    Exactly one of `smiles` or `structure_path` must be provided. Existing generated files are
    protected by default; pass `overwrite=True` to regenerate them.
    """
    safe_id = _validate_compound_id(compound_id)
    mol, structure_source = _load_molecule(smiles=smiles, structure_path=structure_path)
    compound_dir = Path(project_dir) / "compounds" / safe_id

    _ensure_can_initialize(compound_dir, overwrite=overwrite)
    _create_standard_dirs(compound_dir)

    copied_files = _copy_raw_file_groups(
        compound_dir=compound_dir,
        groups=raw_file_groups,
        overwrite=overwrite,
    )
    structure_files = _write_structure_files(
        compound_dir=compound_dir,
        mol=mol,
        overwrite=overwrite,
    )
    metadata = _build_metadata(
        compound_id=safe_id,
        mol=mol,
        structure_source=structure_source,
        compound_dir=compound_dir,
        copied_files=copied_files,
    )
    metadata_path = compound_dir / "metadata.json"
    _write_json(metadata_path, metadata.to_dict(), overwrite=overwrite)

    summary_path = compound_dir / "reports" / "summary.md"
    _write_text(summary_path, _render_summary(metadata), overwrite=overwrite)

    return CompoundArchiveResult(
        compound_dir=compound_dir,
        metadata_path=metadata_path,
        summary_path=summary_path,
        structure_files=tuple(structure_files),
        copied_raw_files=tuple(copied_files),
    )


def _validate_compound_id(compound_id: str) -> str:
    safe_id = compound_id.strip()
    if not safe_id:
        raise StorageError("compound_id 不能为空")
    if any(part in safe_id for part in ("/", "\\", "..")):
        raise StorageError("compound_id 不能包含路径分隔符或 '..'")
    return safe_id


def _load_molecule(
    *,
    smiles: str | None,
    structure_path: str | Path | None,
) -> tuple[Chem.Mol, str]:
    if (smiles is None) == (structure_path is None):
        raise StorageError("请提供 smiles 或 structure_path 二者之一")
    if smiles is not None:
        return parse_smiles(smiles), "smiles"
    path = Path(structure_path)  # type: ignore[arg-type]
    return load_structure(path), str(path)


def _ensure_can_initialize(compound_dir: Path, overwrite: bool) -> None:
    metadata_path = compound_dir / "metadata.json"
    if metadata_path.exists() and not overwrite:
        raise StorageError(f"compound 已存在：{compound_dir}。如需重新生成，请显式传 --overwrite。")


def _create_standard_dirs(compound_dir: Path) -> None:
    for relative in STANDARD_DIRS:
        (compound_dir / relative).mkdir(parents=True, exist_ok=True)


def _write_structure_files(
    *,
    compound_dir: Path,
    mol: Chem.Mol,
    overwrite: bool,
) -> list[Path]:
    info = mol_info(mol)
    structure_dir = compound_dir / "structure"
    smiles_path = structure_dir / "structure.smi"
    mol_path = structure_dir / "structure.mol"
    svg_path = structure_dir / "structure_indexed.svg"

    _write_text(smiles_path, f"{info['smiles']}\n", overwrite=overwrite)
    _write_text(mol_path, Chem.MolToMolBlock(mol), overwrite=overwrite)
    _ensure_writable(svg_path, overwrite=overwrite)
    draw_structure(mol, svg_path, show_atom_index=True)
    return [smiles_path, mol_path, svg_path]


def _copy_raw_file_groups(
    *,
    compound_dir: Path,
    groups: tuple[RawFileGroup, ...],
    overwrite: bool,
) -> list[Path]:
    copied: list[Path] = []
    for group in groups:
        destination_dir = compound_dir / group.destination
        destination_dir.mkdir(parents=True, exist_ok=True)
        for source in group.sources:
            copied.append(_copy_one_file(source, destination_dir, overwrite=overwrite))
    return copied


def _copy_one_file(source: Path, destination_dir: Path, overwrite: bool) -> Path:
    if not source.exists() or not source.is_file():
        raise StorageError(f"原始文件不存在或不是文件：{source}")
    destination = destination_dir / source.name
    _ensure_writable(destination, overwrite=overwrite)
    shutil.copy2(source, destination)
    return destination


def _build_metadata(
    *,
    compound_id: str,
    mol: Chem.Mol,
    structure_source: str,
    compound_dir: Path,
    copied_files: list[Path],
) -> CompoundMetadata:
    info = mol_info(mol)
    copied_relatives = tuple(_relative_to(path, compound_dir) for path in copied_files)
    return CompoundMetadata(
        compound_id=compound_id,
        smiles=str(info["smiles"]),
        formula=str(info["formula"]),
        molecular_weight=float(info["mol_weight"]),
        heavy_atoms=int(info["heavy_atoms"]),
        num_atoms=int(info["num_atoms"]),
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        structure_source=structure_source,
        copied_raw_files=copied_relatives,
    )


def _render_summary(metadata: CompoundMetadata) -> str:
    copied = "\n".join(f"- `{path}`" for path in metadata.copied_raw_files)
    if not copied:
        copied = "- Not provided"
    return f"""# Compound {metadata.compound_id}

## Metadata

- Canonical SMILES: `{metadata.smiles}`
- Formula: {metadata.formula}
- Molecular weight: {metadata.molecular_weight:.3f}
- Heavy atoms: {metadata.heavy_atoms}
- Created at: {metadata.created_at}

## Files

- `metadata.json`
- `structure/structure.smi`
- `structure/structure.mol`
- `structure/structure_indexed.svg`

## Copied raw files

{copied}
""".strip()


def _write_json(path: Path, payload: dict[str, object], overwrite: bool) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_text(path, text, overwrite=overwrite)


def _write_text(path: Path, text: str, overwrite: bool) -> None:
    _ensure_writable(path, overwrite=overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _ensure_writable(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise StorageError(f"文件已存在，未覆盖：{path}")


def _relative_to(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)
