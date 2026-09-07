"""NMR data models, parsing, formatting, and consistency checks."""

from chem_workflow.spectroscopy.nmr.consistency import (
    ConsistencyError,
    SignalCountCheck,
    check_signal_count,
    expected_unique_signals,
)
from chem_workflow.spectroscopy.nmr.formatting import (
    NMRFormatError,
    NMRFormatOptions,
    format_nmr_spectrum,
)
from chem_workflow.spectroscopy.nmr.models import NMRInputError, NMRPeak, NMRSpectrum
from chem_workflow.spectroscopy.nmr.parsing import (
    normalize_multiplicity,
    parse_j_values,
    parse_mestrenova_multiplet_table,
    parse_shift_list,
    parse_shift_range,
)

__all__ = [
    "ConsistencyError",
    "NMRFormatError",
    "NMRFormatOptions",
    "NMRInputError",
    "NMRPeak",
    "NMRSpectrum",
    "SignalCountCheck",
    "check_signal_count",
    "expected_unique_signals",
    "format_nmr_spectrum",
    "normalize_multiplicity",
    "parse_j_values",
    "parse_mestrenova_multiplet_table",
    "parse_shift_list",
    "parse_shift_range",
]
