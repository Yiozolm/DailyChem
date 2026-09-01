"""Compatibility exports for UV-vis domain functions and CLI commands."""

from chem_workflow.interfaces.cli.spectra import uv_app, uv_format
from chem_workflow.spectroscopy.uv import (
    UVBand,
    UVInputError,
    UVSpectrum,
    format_uv,
    parse_uv_peaks,
)

__all__ = [
    "UVBand",
    "UVInputError",
    "UVSpectrum",
    "format_uv",
    "parse_uv_peaks",
    "uv_app",
    "uv_format",
]
