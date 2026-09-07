"""Compatibility exports for IR domain functions and CLI commands."""

from chem_workflow.interfaces.cli.spectra import ir_app, ir_format
from chem_workflow.spectroscopy.ir import (
    IRBand,
    IRInputError,
    IRSpectrum,
    format_ir,
    parse_ir_peaks,
)

__all__ = [
    "IRBand",
    "IRInputError",
    "IRSpectrum",
    "format_ir",
    "ir_app",
    "ir_format",
    "parse_ir_peaks",
]
