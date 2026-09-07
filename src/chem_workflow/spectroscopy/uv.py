"""Phase 10 UV-vis peak list parsing and publication-style formatting.

Input is a list of absorption maxima (nm), each optionally with a molar absorptivity (epsilon),
separated by commas / newlines. Output is a standard UV-vis characterization line:

    UV-vis (MeOH) λmax 254 nm.
    UV-vis (MeOH) λmax 254 nm (ε 12000), 320 nm (ε 4500).
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


class UVInputError(ValueError):
    """UV-vis 输入解析失败时抛出。错误信息会展示给用户，应包含可操作建议。"""


class UVBand(BaseModel):
    """A single UV-vis absorption band."""

    lambda_max: float  # nm
    epsilon: float | None = None  # molar absorptivity (L mol^-1 cm^-1)
    absorbance: float | None = None


class UVSpectrum(BaseModel):
    """A UV-vis spectrum: a solvent plus its absorption bands."""

    solvent: str | None = None  # MeOH / EtOH / CH2Cl2...
    bands: list[UVBand] = Field(default_factory=list)


def parse_uv_peaks(source: str | Path, *, solvent: str | None = None) -> UVSpectrum:
    """Parse a UV-vis peak list into a :class:`UVSpectrum`.

    Each line / comma-separated entry is ``lambda_max`` optionally followed by an epsilon value,
    e.g. ``254 (12000), 320 4500`` or simply ``254, 320``.
    """
    text = _read_source(source)
    if not text.strip():
        raise UVInputError("UV-vis 输入为空；请提供 λmax 列表，例如 254, 320。")

    bands: list[UVBand] = []
    for token in _split_tokens(text):
        numbers = [float(m) for m in _NUMBER_RE.findall(token)]
        if not numbers:
            continue
        epsilon = numbers[1] if len(numbers) > 1 else None
        bands.append(UVBand(lambda_max=numbers[0], epsilon=epsilon))

    if not bands:
        raise UVInputError(f"未能从输入解析出任何 λmax：{text!r}")
    return UVSpectrum(solvent=(solvent.strip() if solvent else None) or None, bands=bands)


def format_uv(spectrum: UVSpectrum, *, sort_ascending: bool = True) -> str:
    """Render a :class:`UVSpectrum` as a standard UV-vis characterization line."""
    if not spectrum.bands:
        raise UVInputError("无法格式化没有任何 band 的 UV-vis 谱。")
    bands = (
        sorted(spectrum.bands, key=lambda b: b.lambda_max)
        if sort_ascending
        else list(spectrum.bands)
    )
    rendered = [_format_band(band) for band in bands]
    head = "UV-vis"
    if spectrum.solvent:
        head += f" ({spectrum.solvent})"
    return f"{head} λmax {', '.join(rendered)}."


def _format_band(band: UVBand) -> str:
    value = f"{_format_number(band.lambda_max)} nm"
    if band.epsilon is not None:
        value += f" (ε {_format_number(band.epsilon)})"
    return value


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _split_tokens(text: str) -> list[str]:
    raw = re.split(r"[,;\n]", text)
    return [chunk.strip() for chunk in raw if chunk.strip()]


def _read_source(source: str | Path) -> str:
    if isinstance(source, Path):
        if not source.exists():
            raise UVInputError(f"找不到 UV-vis 输入文件：{source}")
        return source.read_text(encoding="utf-8")
    return source
