"""Phase 10 MS / HRMS calculation and publication-style formatting.

HRMS calculated m/z can come from two sources:

1. From structure: ``compute_hrms`` takes SMILES / a structure file plus an adduct, and uses RDKit
   monoisotopic masses to compute the ion m/z and ion formula.
2. Manual: ``hrms_from_manual`` takes a user-provided calculated m/z and ion formula directly.

Both paths produce an :class:`HRMSResult` that :func:`format_hrms` renders into a standard line:

    HRMS (ESI) m/z calculated for C9H10O2Na [M + Na]+ 173.0573, found 173.0570 (ppm error -1.7).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from rdkit import Chem
from rdkit.Chem.Descriptors import ExactMolWt

from chem_workflow.compounds.structure import StructureInputError, load_structure, parse_smiles


class MSInputError(ValueError):
    """MS/HRMS 输入解析失败时抛出。错误信息会展示给用户，应包含可操作建议。"""


# Monoisotopic masses (most abundant isotope), in Da.
_ELECTRON_MASS = 0.000548579909
_ATOM_MONOISOTOPIC_MASS: dict[str, float] = {
    "H": 1.0078250319,
    "C": 12.0,
    "N": 14.0030740052,
    "O": 15.9949146221,
    "F": 18.9984032,
    "Na": 22.98976928,
    "K": 38.96370649,
    "Cl": 34.96885268,
}


class AdductSpec(BaseModel):
    """A single, charge-1 adduct definition for HRMS calculation."""

    display: str  # e.g. "[M + Na]+"
    charge_sign: int  # +1 or -1
    atom_delta: dict[str, int] = Field(default_factory=dict)  # atoms added (+) / removed (-)


# Common, singly-charged adducts (MVP: n = 1, z = 1).
_ADDUCTS: dict[str, AdductSpec] = {
    "[M+H]+": AdductSpec(display="[M + H]+", charge_sign=1, atom_delta={"H": 1}),
    "[M+Na]+": AdductSpec(display="[M + Na]+", charge_sign=1, atom_delta={"Na": 1}),
    "[M+K]+": AdductSpec(display="[M + K]+", charge_sign=1, atom_delta={"K": 1}),
    "[M+NH4]+": AdductSpec(display="[M + NH4]+", charge_sign=1, atom_delta={"N": 1, "H": 4}),
    "[M-H]-": AdductSpec(display="[M - H]-", charge_sign=-1, atom_delta={"H": -1}),
    "[M+H-H2O]+": AdductSpec(
        display="[M + H - H2O]+", charge_sign=1, atom_delta={"H": -1, "O": -1}
    ),
}

# Ion formula rendering: C and H first, non-metal heteroatoms alphabetically, cations (Na/K) last.
# This matches the conventional HRMS style "C9H10O2Na" rather than strict Hill "C9H10NaO2".
_FORMULA_LEAD = ("C", "H")
_FORMULA_TRAIL = ("Na", "K")


class HRMSResult(BaseModel):
    """A computed HRMS entry ready for publication-style rendering."""

    ionization: str = "ESI"
    adduct: str  # display form, e.g. "[M + Na]+"
    ion_formula: str  # e.g. "C9H10O2Na"
    calculated_mz: float
    found_mz: float | None = None
    ppm_error: float | None = None


def available_adducts() -> tuple[str, ...]:
    """Return the supported adduct keys (e.g. ``"[M+Na]+"``)."""
    return tuple(_ADDUCTS)


def compute_hrms(
    *,
    smiles: str | None = None,
    structure_path: str | Path | None = None,
    adduct: str = "[M+Na]+",
    ionization: str = "ESI",
    found_mz: float | None = None,
) -> HRMSResult:
    """Compute an HRMS entry from a structure (SMILES or file) and an adduct."""
    mol = _load_mol(smiles=smiles, structure_path=structure_path)
    spec = _resolve_adduct(adduct)

    neutral_counts = _formula_counts(mol)
    ion_counts = _apply_atom_delta(neutral_counts, spec.atom_delta, adduct=adduct)
    ion_formula = _render_formula(ion_counts)

    neutral_mass = ExactMolWt(mol)
    delta_mass = sum(
        _ATOM_MONOISOTOPIC_MASS[symbol] * count for symbol, count in spec.atom_delta.items()
    )
    calculated_mz = neutral_mass + delta_mass - spec.charge_sign * _ELECTRON_MASS

    return _build_result(
        ionization=ionization,
        spec=spec,
        ion_formula=ion_formula,
        calculated_mz=calculated_mz,
        found_mz=found_mz,
    )


def hrms_from_manual(
    *,
    ion_formula: str,
    calculated_mz: float,
    adduct: str = "[M+Na]+",
    ionization: str = "ESI",
    found_mz: float | None = None,
) -> HRMSResult:
    """Build an HRMS entry from a user-provided calculated m/z and ion formula."""
    spec = _resolve_adduct(adduct)
    cleaned_formula = ion_formula.strip()
    if not cleaned_formula:
        raise MSInputError("ion_formula 为空；请提供离子式，例如 C9H10O2Na。")
    if calculated_mz <= 0:
        raise MSInputError("calculated_mz 必须为正数。")
    return _build_result(
        ionization=ionization,
        spec=spec,
        ion_formula=cleaned_formula,
        calculated_mz=calculated_mz,
        found_mz=found_mz,
    )


def ppm_error(calculated_mz: float, found_mz: float) -> float:
    """Return signed mass error in ppm, rounded to 1 decimal."""
    if calculated_mz <= 0:
        raise MSInputError("calculated_mz 必须为正数。")
    return round((found_mz - calculated_mz) / calculated_mz * 1e6, 1)


def format_hrms(result: HRMSResult, *, mz_decimals: int = 4) -> str:
    """Render an :class:`HRMSResult` as a standard HRMS characterization line."""
    calc = f"{result.calculated_mz:.{mz_decimals}f}"
    line = (
        f"HRMS ({result.ionization}) m/z calculated for "
        f"{result.ion_formula} {result.adduct} {calc}"
    )
    if result.found_mz is not None:
        line += f", found {result.found_mz:.{mz_decimals}f}"
        if result.ppm_error is not None:
            line += f" (ppm error {result.ppm_error})"
    return line + "."


def _build_result(
    *,
    ionization: str,
    spec: AdductSpec,
    ion_formula: str,
    calculated_mz: float,
    found_mz: float | None,
) -> HRMSResult:
    error = ppm_error(calculated_mz, found_mz) if found_mz is not None else None
    return HRMSResult(
        ionization=ionization.strip() or "ESI",
        adduct=spec.display,
        ion_formula=ion_formula,
        calculated_mz=round(calculated_mz, 6),
        found_mz=found_mz,
        ppm_error=error,
    )


def _load_mol(*, smiles: str | None, structure_path: str | Path | None) -> Chem.Mol:
    if smiles and structure_path:
        raise MSInputError("smiles 与 structure_path 二选一，不能同时提供。")
    try:
        if smiles:
            return parse_smiles(smiles)
        if structure_path:
            return load_structure(structure_path)
    except StructureInputError as e:
        raise MSInputError(str(e)) from e
    raise MSInputError("请提供 smiles 或 structure_path 之一。")


def _resolve_adduct(adduct: str) -> AdductSpec:
    key = adduct.replace(" ", "")
    spec = _ADDUCTS.get(key)
    if spec is None:
        supported = ", ".join(_ADDUCTS)
        raise MSInputError(f"暂不支持 adduct {adduct!r}。已支持：{supported}。")
    return spec


def _formula_counts(mol: Chem.Mol) -> dict[str, int]:
    counts: dict[str, int] = {}
    mol_with_h = Chem.AddHs(mol)
    for atom in mol_with_h.GetAtoms():
        counts[atom.GetSymbol()] = counts.get(atom.GetSymbol(), 0) + 1
    return counts


def _apply_atom_delta(
    counts: dict[str, int], delta: dict[str, int], *, adduct: str
) -> dict[str, int]:
    result = dict(counts)
    for symbol, change in delta.items():
        result[symbol] = result.get(symbol, 0) + change
        if result[symbol] < 0:
            raise MSInputError(
                f"adduct {adduct!r} 需要移除 {symbol}，但分子中该原子不足。"
            )
        if result[symbol] == 0:
            del result[symbol]
    return result


def _render_formula(counts: dict[str, int]) -> str:
    parts: list[str] = []
    for symbol in _FORMULA_LEAD:
        if symbol in counts:
            parts.append(_formula_token(symbol, counts[symbol]))
    middle = sorted(
        s for s in counts if s not in _FORMULA_LEAD and s not in _FORMULA_TRAIL
    )
    for symbol in middle:
        parts.append(_formula_token(symbol, counts[symbol]))
    for symbol in _FORMULA_TRAIL:
        if symbol in counts:
            parts.append(_formula_token(symbol, counts[symbol]))
    return "".join(parts)


def _formula_token(symbol: str, count: int) -> str:
    return symbol if count == 1 else f"{symbol}{count}"
