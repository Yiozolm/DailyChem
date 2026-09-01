"""Typer commands for HRMS, IR, and UV-vis features."""

from __future__ import annotations

from pathlib import Path

import typer

from chem_workflow.spectroscopy.hrms import (
    MSInputError,
    compute_hrms,
    format_hrms,
    hrms_from_manual,
)
from chem_workflow.spectroscopy.ir import IRInputError, format_ir, parse_ir_peaks
from chem_workflow.spectroscopy.uv import UVInputError, format_uv, parse_uv_peaks

ms_app = typer.Typer(help="MS / HRMS 数据相关命令", no_args_is_help=True)
ir_app = typer.Typer(help="IR 数据相关命令", no_args_is_help=True)
uv_app = typer.Typer(help="UV-vis 数据相关命令", no_args_is_help=True)


@ms_app.command("hrms")
def ms_hrms(
    smiles: str | None = typer.Option(
        None, "--smiles", "-s", help="目标化合物 SMILES（自动计算 calc m/z）"
    ),
    structure: Path | None = typer.Option(
        None, "--structure", help="结构文件路径（.mol/.sdf/.cdx/.cdxml/.smi，自动计算）"
    ),
    ion_formula: str | None = typer.Option(
        None, "--ion-formula", help="手动模式：离子式，例如 C9H10O2Na"
    ),
    calc: float | None = typer.Option(
        None, "--calc", help="手动模式：用户提供的 calculated m/z"
    ),
    adduct: str = typer.Option("[M+Na]+", "--adduct", "-a", help="加合方式，例如 [M+Na]+"),
    ionization: str = typer.Option("ESI", "--ionization", help="电离方式：ESI / EI / APCI..."),
    found: float | None = typer.Option(None, "--found", help="实测 m/z，用于计算 ppm error"),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出"),
    out: Path | None = typer.Option(None, "--out", "-o", help="输出到文件（JSON 隐含 --json）"),
) -> None:
    """生成 HRMS 表征文本：可从结构自动计算，也可手动提供 calc m/z。"""
    try:
        if ion_formula is not None or calc is not None:
            if ion_formula is None or calc is None:
                raise MSInputError("手动模式需要同时提供 --ion-formula 和 --calc。")
            result = hrms_from_manual(
                ion_formula=ion_formula,
                calculated_mz=calc,
                adduct=adduct,
                ionization=ionization,
                found_mz=found,
            )
        else:
            result = compute_hrms(
                smiles=smiles,
                structure_path=structure,
                adduct=adduct,
                ionization=ionization,
                found_mz=found,
            )
    except MSInputError as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    payload = result.model_dump_json(indent=2) if (as_json or out is not None) else format_hrms(
        result
    )
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"已写入 {out}")
        return
    typer.echo(payload)


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


__all__ = ["ir_app", "ir_format", "ms_app", "ms_hrms", "uv_app", "uv_format"]
