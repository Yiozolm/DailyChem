"""Compatibility exports for HRMS domain functions and CLI commands."""

from chem_workflow.interfaces.cli.spectra import ms_app, ms_hrms
from chem_workflow.spectroscopy.hrms import (
    AdductSpec,
    HRMSResult,
    MSInputError,
    available_adducts,
    compute_hrms,
    format_hrms,
    hrms_from_manual,
    ppm_error,
)

__all__ = [
    "AdductSpec",
    "HRMSResult",
    "MSInputError",
    "available_adducts",
    "compute_hrms",
    "format_hrms",
    "hrms_from_manual",
    "ms_app",
    "ms_hrms",
    "ppm_error",
]
