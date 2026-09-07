"""Compound archive inputs, results, and metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
    """Paths written by ``init_compound_archive``."""

    compound_dir: Path
    metadata_path: Path
    summary_path: Path
    structure_files: tuple[Path, ...]
    copied_raw_files: tuple[Path, ...]


@dataclass(frozen=True)
class CompoundMetadata:
    """Serializable compound metadata for ``metadata.json``."""

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


__all__ = [
    "CompoundArchiveResult",
    "CompoundMetadata",
    "RawFileGroup",
    "StorageError",
]
