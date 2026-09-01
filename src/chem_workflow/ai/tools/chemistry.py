"""Read-only typed tools backed by deterministic chemistry functions."""

from __future__ import annotations

from agents import function_tool

from chem_workflow.compounds.structure import mol_info, parse_smiles
from chem_workflow.spectroscopy.hrms import compute_hrms, format_hrms
from chem_workflow.spectroscopy.ir import format_ir, parse_ir_peaks
from chem_workflow.spectroscopy.uv import format_uv, parse_uv_peaks


def get_structure_metadata(smiles: str) -> dict[str, object]:
    """Return canonical SMILES, formula, molecular weight, and atom counts."""
    return mol_info(parse_smiles(smiles))


def calculate_hrms_text(
    smiles: str,
    adduct: str = "[M+Na]+",
    ionization: str = "ESI",
    found_mz: float | None = None,
) -> str:
    """Calculate and format an HRMS characterization line from a structure."""
    return format_hrms(
        compute_hrms(
            smiles=smiles,
            adduct=adduct,
            ionization=ionization,
            found_mz=found_mz,
        )
    )


def normalize_ir_text(peaks: str, technique: str = "neat") -> str:
    """Parse and format a user-provided IR peak list without inventing peaks."""
    return format_ir(parse_ir_peaks(peaks, technique=technique))


def normalize_uv_text(peaks: str, solvent: str | None = None) -> str:
    """Parse and format a user-provided UV-vis peak list without inventing bands."""
    return format_uv(parse_uv_peaks(peaks, solvent=solvent))


structure_metadata_tool = function_tool(get_structure_metadata)
hrms_text_tool = function_tool(calculate_hrms_text)
ir_text_tool = function_tool(normalize_ir_text)
uv_text_tool = function_tool(normalize_uv_text)

READ_ONLY_CHEMISTRY_TOOLS = (
    structure_metadata_tool,
    hrms_text_tool,
    ir_text_tool,
    uv_text_tool,
)

__all__ = [
    "READ_ONLY_CHEMISTRY_TOOLS",
    "calculate_hrms_text",
    "get_structure_metadata",
    "hrms_text_tool",
    "ir_text_tool",
    "normalize_ir_text",
    "normalize_uv_text",
    "structure_metadata_tool",
    "uv_text_tool",
]
