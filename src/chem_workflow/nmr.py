"""Compatibility exports for :mod:`chem_workflow.spectroscopy.nmr`."""

from chem_workflow.spectroscopy.nmr.models import NMRInputError, NMRPeak, NMRSpectrum
from chem_workflow.spectroscopy.nmr.parsing import (
    KNOWN_MULTIPLICITIES,
    normalize_multiplicity,
    parse_j_values,
    parse_mestrenova_multiplet_table,
    parse_shift_list,
    parse_shift_range,
)

__all__ = [
    "KNOWN_MULTIPLICITIES",
    "NMRInputError",
    "NMRPeak",
    "NMRSpectrum",
    "normalize_multiplicity",
    "parse_j_values",
    "parse_mestrenova_multiplet_table",
    "parse_shift_list",
    "parse_shift_range",
]
