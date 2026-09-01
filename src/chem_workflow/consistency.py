"""Compatibility exports for NMR signal-count consistency checks."""

from chem_workflow.spectroscopy.nmr.consistency import (
    ConsistencyError,
    SignalCountCheck,
    check_signal_count,
    expected_unique_signals,
)

__all__ = [
    "ConsistencyError",
    "SignalCountCheck",
    "check_signal_count",
    "expected_unique_signals",
]
