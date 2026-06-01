"""Phase 10 UV-vis peak list parsing and publication-style formatting.

Input is a list of absorption maxima (nm), each optionally with a molar absorptivity (epsilon),
separated by commas / newlines. Output is a standard UV-vis characterization line:

    UV-vis (MeOH) λmax 254 nm.
    UV-vis (MeOH) λmax 254 nm (ε 12000), 320 nm (ε 4500).
"""

from __future__ import annotations

import re
from pathlib import Path

import typer
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


uv_app = typer.Typer(help="UV-vis 数据相关命令", no_args_is_help=True)


@uv_app.command("format")
def uv_format(
    path: Path | None = typer.Argument(
        None, help="UV-vis λmax 列表文件（逗号/换行分隔）", exists=False
    ),
    inline: str | None = typer.Option(
        None, "--inline", "-i", help="直接贴 λmax 列表，与 path 二选一"
    ),
    solvent: str | None = typer.Option(None, "--solvent", "-s", help="溶剂，例如 MeOH / EtOH"),
    preserve_order: bool = typer.Option(
        False, "--preserve-order", help="保留输入顺序，不按 λmax 从低到高排序"
    ),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出"),
    out: Path | None = typer.Option(None, "--out", "-o", help="输出到文件（JSON 隐含 --json）"),
) -> None:
    """把 UV-vis λmax 列表格式化成标准表征文本。"""
    try:
        source: str | Path
        if inline is not None:
            source = inline
        elif path is not None:
            source = path
        else:
            raise UVInputError("请提供 λmax 列表文件路径或 --inline 文本。")
        spectrum = parse_uv_peaks(source, solvent=solvent)
        text = format_uv(spectrum, sort_ascending=not preserve_order)
    except UVInputError as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    payload = spectrum.model_dump_json(indent=2) if (as_json or out is not None) else text
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"已写入 {out}")
        return
    typer.echo(payload)
