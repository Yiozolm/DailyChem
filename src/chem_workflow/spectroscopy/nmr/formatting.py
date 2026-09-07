"""Publication-style NMR text formatting."""

from __future__ import annotations

from dataclasses import dataclass

from chem_workflow.spectroscopy.nmr.models import NMRPeak, NMRSpectrum


class NMRFormatError(ValueError):
    """Raised when an NMR spectrum cannot be formatted safely."""


@dataclass(frozen=True)
class NMRFormatOptions:
    """Controls publication-style NMR rendering."""

    include_assignment: bool = False
    sort_descending: bool = True
    include_solvent: bool = True
    include_frequency: bool = True
    proton_shift_decimals: int = 2
    carbon_shift_decimals: int = 1
    hetero_shift_decimals: int = 1
    j_decimals: int = 1


def format_nmr_spectrum(
    spectrum: NMRSpectrum,
    options: NMRFormatOptions | None = None,
) -> str:
    """Format an `NMRSpectrum` as a standard characterization line.

    1H gets full multiplicity/J/integration rendering. 13C / 19F / 31P are rendered as shift lists
    (no integration), which matches common publication style for those nuclei.
    """
    opts = options or NMRFormatOptions()
    if not spectrum.peaks:
        raise NMRFormatError("Cannot format an NMR spectrum without peaks.")

    if spectrum.nucleus == "1H":
        return _format_1h_nmr(spectrum, opts)
    if spectrum.nucleus == "13C":
        return _format_shift_list_nmr(spectrum, opts, opts.carbon_shift_decimals)
    if spectrum.nucleus in ("19F", "31P"):
        return _format_shift_list_nmr(spectrum, opts, opts.hetero_shift_decimals)
    raise NMRFormatError(
        f"Formatting for {spectrum.nucleus!r} is not implemented yet; "
        "supported nuclei: 1H, 13C, 19F, 31P."
    )


def _format_1h_nmr(spectrum: NMRSpectrum, options: NMRFormatOptions) -> str:
    peaks = _ordered_peaks(spectrum.peaks, options.sort_descending)
    rendered = [_format_1h_peak(peak, options) for peak in peaks]
    return f"{_format_header(spectrum, options)} δ {', '.join(rendered)}."


def _format_shift_list_nmr(
    spectrum: NMRSpectrum,
    options: NMRFormatOptions,
    decimals: int,
) -> str:
    peaks = _ordered_peaks(spectrum.peaks, options.sort_descending)
    rendered = [_format_shift_peak(peak, options, decimals) for peak in peaks]
    return f"{_format_header(spectrum, options)} δ {', '.join(rendered)}."


def _ordered_peaks(peaks: list[NMRPeak], sort_descending: bool) -> list[NMRPeak]:
    if not sort_descending:
        return list(peaks)
    return sorted(peaks, key=lambda peak: peak.shift_ppm, reverse=True)


def _format_header(spectrum: NMRSpectrum, options: NMRFormatOptions) -> str:
    parts: list[str] = []
    if options.include_frequency and spectrum.frequency_mhz is not None:
        parts.append(f"{_format_frequency(spectrum.frequency_mhz)} MHz")
    if options.include_solvent and spectrum.solvent:
        parts.append(spectrum.solvent)

    head = f"{spectrum.nucleus} NMR"
    if parts:
        head += f" ({', '.join(parts)})"
    return head


def _format_1h_peak(peak: NMRPeak, options: NMRFormatOptions) -> str:
    shift = _format_decimal(peak.shift_ppm, options.proton_shift_decimals)
    details: list[str] = []
    if peak.multiplicity:
        details.append(peak.multiplicity)
    if peak.j_hz:
        details.append(_format_j_values(peak.j_hz, options.j_decimals))
    if peak.integration is not None:
        details.append(f"{_format_integration(peak.integration)}H")
    if options.include_assignment and peak.assignment:
        details.append(f"assignment {peak.assignment}")

    if not details:
        return shift
    return f"{shift} ({', '.join(details)})"


def _format_shift_peak(peak: NMRPeak, options: NMRFormatOptions, decimals: int) -> str:
    shift = _format_decimal(peak.shift_ppm, decimals)
    if options.include_assignment and peak.assignment:
        return f"{shift} ({peak.assignment})"
    return shift


def _format_j_values(values: list[float], decimals: int) -> str:
    rendered = ", ".join(_format_decimal(value, decimals) for value in values)
    return f"J = {rendered} Hz"


def _format_integration(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return _strip_trailing_zeros(f"{value:.2f}")


def _format_frequency(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return _strip_trailing_zeros(f"{value:.2f}")


def _format_decimal(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def _strip_trailing_zeros(text: str) -> str:
    return text.rstrip("0").rstrip(".")
