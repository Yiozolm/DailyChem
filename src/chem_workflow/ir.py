"""Phase 10 IR peak list parsing and publication-style formatting.

Input is a simple list of wavenumbers (cm^-1), optionally with an intensity label, separated by
commas / whitespace / newlines. Output is a standard IR characterization line:

    IR (neat) νmax 3050, 2920, 1715, 1600, 1450 cm⁻¹.
"""

from __future__ import annotations

import re
from pathlib import Path

import typer
from pydantic import BaseModel, Field

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_INTENSITY_RE = re.compile(r"^(s|m|w|vs|vw|br|sh)$", re.IGNORECASE)


class IRInputError(ValueError):
    """IR 输入解析失败时抛出。错误信息会展示给用户，应包含可操作建议。"""


class IRBand(BaseModel):
    """A single IR absorption band."""

    wavenumber: float  # cm^-1
    intensity: str | None = None  # s / m / w / vs / vw / br / sh
    assignment: str | None = None


class IRSpectrum(BaseModel):
    """An IR spectrum: a measurement technique plus its absorption bands."""

    technique: str = "neat"  # neat / KBr / ATR / film
    bands: list[IRBand] = Field(default_factory=list)


def parse_ir_peaks(source: str | Path, *, technique: str = "neat") -> IRSpectrum:
    """Parse an IR peak list into an :class:`IRSpectrum`.

    Accepts comma / whitespace / newline separated wavenumbers, each optionally followed by an
    intensity label, e.g. ``3050 (s), 2920 m, 1715``.
    """
    text = _read_source(source)
    if not text.strip():
        raise IRInputError("IR 输入为空；请提供波数列表，例如 3050, 2920, 1715。")

    bands: list[IRBand] = []
    for token in _split_tokens(text):
        wavenumber = _extract_wavenumber(token)
        if wavenumber is None:
            continue
        bands.append(IRBand(wavenumber=wavenumber, intensity=_extract_intensity(token)))

    if not bands:
        raise IRInputError(f"未能从输入解析出任何波数：{text!r}")
    return IRSpectrum(technique=technique.strip() or "neat", bands=bands)


def format_ir(
    spectrum: IRSpectrum,
    *,
    sort_descending: bool = True,
    include_intensity: bool = False,
) -> str:
    """Render an :class:`IRSpectrum` as a standard IR characterization line."""
    if not spectrum.bands:
        raise IRInputError("无法格式化没有任何 band 的 IR 谱。")
    bands = (
        sorted(spectrum.bands, key=lambda b: b.wavenumber, reverse=True)
        if sort_descending
        else list(spectrum.bands)
    )
    rendered = [_format_band(band, include_intensity=include_intensity) for band in bands]
    return f"IR ({spectrum.technique}) νmax {', '.join(rendered)} cm⁻¹."


def _format_band(band: IRBand, *, include_intensity: bool) -> str:
    value = _format_wavenumber(band.wavenumber)
    if include_intensity and band.intensity:
        return f"{value} ({band.intensity})"
    return value


def _format_wavenumber(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _split_tokens(text: str) -> list[str]:
    # Split on commas, semicolons, and newlines; keep intensity attached to its number.
    raw = re.split(r"[,;\n]", text)
    return [chunk.strip() for chunk in raw if chunk.strip()]


def _extract_wavenumber(token: str) -> float | None:
    match = _NUMBER_RE.search(token)
    if match is None:
        return None
    return float(match.group())


def _extract_intensity(token: str) -> str | None:
    # Look at trailing word characters / parenthesised label after the number.
    leftover = _NUMBER_RE.sub(" ", token)
    for word in leftover.replace("(", " ").replace(")", " ").split():
        if _INTENSITY_RE.match(word):
            return word.lower()
    return None


def _read_source(source: str | Path) -> str:
    if isinstance(source, Path):
        if not source.exists():
            raise IRInputError(f"找不到 IR 输入文件：{source}")
        return source.read_text(encoding="utf-8")
    return source


ir_app = typer.Typer(help="IR 数据相关命令", no_args_is_help=True)


@ir_app.command("format")
def ir_format(
    path: Path | None = typer.Argument(
        None, help="IR 波数列表文件（逗号/空白/换行分隔）", exists=False
    ),
    inline: str | None = typer.Option(
        None, "--inline", "-i", help="直接贴波数列表，与 path 二选一"
    ),
    technique: str = typer.Option("neat", "--technique", "-t", help="测量方式：neat / KBr / ATR"),
    include_intensity: bool = typer.Option(
        False, "--include-intensity", help="在输出中保留强度标签"
    ),
    preserve_order: bool = typer.Option(
        False, "--preserve-order", help="保留输入顺序，不按波数从高到低排序"
    ),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出"),
    out: Path | None = typer.Option(None, "--out", "-o", help="输出到文件（JSON 隐含 --json）"),
) -> None:
    """把 IR 波数列表格式化成标准表征文本。"""
    try:
        source: str | Path
        if inline is not None:
            source = inline
        elif path is not None:
            source = path
        else:
            raise IRInputError("请提供波数列表文件路径或 --inline 文本。")
        spectrum = parse_ir_peaks(source, technique=technique)
        text = format_ir(
            spectrum,
            sort_descending=not preserve_order,
            include_intensity=include_intensity,
        )
    except IRInputError as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    payload = spectrum.model_dump_json(indent=2) if (as_json or out is not None) else text
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"已写入 {out}")
        return
    typer.echo(payload)
