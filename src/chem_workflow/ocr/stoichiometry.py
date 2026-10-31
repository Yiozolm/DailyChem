"""Unit-aware consistency checks for an OCR-transcribed reagent table.

The checks never change values. They only explain which numbers disagree so a chemist can
look at the photo again. Handwritten ``µ`` is often read as ``m``; a 1000x disagreement is
therefore reported as a likely unit-prefix error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from chem_workflow.ocr.models import OCRTableRow

QuantityKind = Literal["amount", "mass", "volume"]

# Base units are mol, g, and mL.
_UNITS: dict[str, tuple[QuantityKind, float]] = {
    "mol": ("amount", 1.0),
    "mmol": ("amount", 1e-3),
    "μmol": ("amount", 1e-6),
    "nmol": ("amount", 1e-9),
    "kg": ("mass", 1e3),
    "g": ("mass", 1.0),
    "mg": ("mass", 1e-3),
    "μg": ("mass", 1e-6),
    "L": ("volume", 1e3),
    "mL": ("volume", 1.0),
    "μL": ("volume", 1e-3),
}
_UNIT_ALIASES = {unit.lower(): unit for unit in _UNITS}
_DISPLAY_UNITS: dict[QuantityKind, tuple[str, ...]] = {
    "amount": ("mol", "mmol", "μmol", "nmol"),
    "mass": ("g", "mg", "μg"),
    "volume": ("L", "mL", "μL"),
}

UNIT_PATTERN = r"(?:mmol|[μµu]mol|nmol|mol|kg|mg|[μµu]g|g|ml|[μµu]l|l)"
QUANTITY_PATTERN = re.compile(
    rf"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>{UNIT_PATTERN})(?![a-z])", flags=re.I
)
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")

REL_TOL = 0.05


@dataclass(frozen=True)
class Quantity:
    """A parsed value with its unit and value converted to mol, g, or mL."""

    value: float
    unit: str
    kind: QuantityKind
    base: float
    # Number exactly as written, so "3.00 mmol" keeps its significant figures.
    text: str = ""

    def display(self) -> str:
        return f"{self.text or _format_number(self.value)} {self.unit}"


def canonical_unit(raw: str) -> str | None:
    """Map OCR spellings (``ul``, ``µL``, ``ML``) to one canonical unit symbol."""
    lowered = raw.lower().replace("µ", "μ")
    if lowered.startswith("u") and lowered != "u":
        lowered = "μ" + lowered[1:]
    return _UNIT_ALIASES.get(lowered)


def parse_quantity(text: str | None) -> Quantity | None:
    """Return the first ``number + unit`` in ``text``."""
    if not text:
        return None
    match = QUANTITY_PATTERN.search(text)
    if match is None:
        return None
    unit = canonical_unit(match.group("unit"))
    if unit is None:
        return None
    kind, factor = _UNITS[unit]
    text = match.group("value")
    value = float(text)
    return Quantity(value=value, unit=unit, kind=kind, base=value * factor, text=text)


def parse_number(text: str | None) -> float | None:
    """Return the first plain number in ``text``."""
    if not text:
        return None
    match = _NUMBER_PATTERN.search(text)
    return float(match.group(0)) if match else None


def format_quantity(base: float, kind: QuantityKind) -> str:
    """Format a base-unit value with the prefix that keeps it in [1, 1000)."""
    units = _DISPLAY_UNITS[kind]
    for unit in units:
        value = base / _UNITS[unit][1]
        if value >= 1:
            return f"{_format_number(value)} {unit}"
    unit = units[-1]
    return f"{_format_number(base / _UNITS[unit][1])} {unit}"


def check_material_table(rows: list[OCRTableRow]) -> list[str]:
    """Check n = m/M, V = m/d, and equivalents for every table row."""
    messages: list[str] = []
    for row in rows:
        molar_mass = parse_number(row.molar_mass)
        mass = _quantity_of_kind(row.mass, "mass")
        amount = _quantity_of_kind(row.amount, "amount")
        volume = _quantity_of_kind(row.volume, "volume")
        density = parse_number(row.density)
        if molar_mass and mass and amount:
            messages.extend(
                _compare(row.name, "n", amount, mass.base / molar_mass, "m/M")
            )
        if density and mass and volume:
            messages.extend(_compare(row.name, "V", volume, mass.base / density, "m/d"))

    limiting = limiting_amount(rows)
    if limiting is None:
        return messages
    for row in rows:
        equivalents = parse_number(row.equivalents)
        amount = best_amount(row)
        if equivalents is None or amount is None or _close(equivalents, 1.0):
            continue
        ratio = amount / limiting
        if not _close(ratio, equivalents):
            messages.append(
                f"{row.name}：当量写作 {row.equivalents}，按物质的量计算为 "
                f"{_format_number(ratio)} equiv，请核对。"
            )
    return messages


def check_yield(
    rows: list[OCRTableRow],
    yield_mass: str | None,
    yield_percent: str | None,
    product_mw: float | None = None,
) -> list[str]:
    """Check the recorded yield against the limiting reagent and, if known, the product MW."""
    messages: list[str] = []
    percent = parse_number(yield_percent) if yield_percent and "%" in yield_percent else None
    if percent is not None and percent > 100:
        messages.append(
            f"产率 {yield_percent} 超过 100%，请核对产量（例如溶剂未除尽）或限量底物用量。"
        )
    mass = _quantity_of_kind(yield_mass, "mass")
    limiting = limiting_amount(rows)
    if mass is None or limiting is None:
        return messages
    limiting_text = format_quantity(limiting, "amount")
    if product_mw:
        calculated = mass.base / (limiting * product_mw) * 100
        if percent is None:
            messages.append(
                f"按产物 M = {product_mw:.2f} g/mol、限量底物 {limiting_text} 计算，"
                f"{mass.display()} 对应产率 {calculated:.1f}%。"
            )
        elif abs(calculated - percent) > max(1.0, REL_TOL * calculated):
            messages.append(
                f"记录产率 {yield_percent}，但按产物 M = {product_mw:.2f} g/mol、"
                f"限量底物 {limiting_text} 计算，{mass.display()} 对应 {calculated:.1f}%，请核对。"
            )
    elif percent:
        implied = mass.base / (percent / 100 * limiting)
        messages.append(
            f"按产量 {mass.display()}、产率 {yield_percent}、限量底物 {limiting_text} 反推产物 "
            f"M ≈ {implied:.1f} g/mol；请与产物分子量对照。"
        )
    return messages


def best_amount(row: OCRTableRow) -> float | None:
    """Prefer m/M (two independent numbers) over the written n."""
    molar_mass = parse_number(row.molar_mass)
    mass = _quantity_of_kind(row.mass, "mass")
    if molar_mass and mass:
        return mass.base / molar_mass
    amount = _quantity_of_kind(row.amount, "amount")
    return amount.base if amount else None


def limiting_amount(rows: list[OCRTableRow]) -> float | None:
    """Return mol of the first 1.0-equivalent row."""
    for row in rows:
        equivalents = parse_number(row.equivalents)
        if equivalents is not None and _close(equivalents, 1.0):
            amount = best_amount(row)
            if amount:
                return amount
    return None


def _compare(
    name: str, label: str, written: Quantity, expected_base: float, formula: str
) -> list[str]:
    ratio = written.base / expected_base
    if _close(ratio, 1.0):
        return []
    expected = format_quantity(expected_base, written.kind)
    if _close(ratio, 1e3) or _close(ratio, 1e-3):
        return [
            f"{name}：{label} 写作 {written.display()}，但 {formula} = {expected}，相差 1000 倍；"
            "很可能是手写 μ/m 单位前缀识别错误，请对照照片核对。"
        ]
    return [f"{name}：{label} 写作 {written.display()}，但 {formula} = {expected}，请核对。"]


def _quantity_of_kind(text: str | None, kind: QuantityKind) -> Quantity | None:
    quantity = parse_quantity(text)
    return quantity if quantity is not None and quantity.kind == kind else None


def _close(value: float, target: float) -> bool:
    return abs(value - target) <= REL_TOL * abs(target)


def _format_number(value: float) -> str:
    return f"{value:.4g}"


__all__ = [
    "QUANTITY_PATTERN",
    "Quantity",
    "best_amount",
    "canonical_unit",
    "check_material_table",
    "check_yield",
    "format_quantity",
    "limiting_amount",
    "parse_number",
    "parse_quantity",
]
