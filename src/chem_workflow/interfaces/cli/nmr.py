"""NMR parsing, formatting, assignment, and consistency CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from chem_workflow.compounds.structure import (
    StructureInputError,
    load_structure,
    parse_smiles,
)
from chem_workflow.spectroscopy.assignment import (
    AssignmentError,
    assign_nmr,
    load_assignment_rules,
    render_assignment_draft,
)
from chem_workflow.spectroscopy.nmr.consistency import ConsistencyError, check_signal_count
from chem_workflow.spectroscopy.nmr.formatting import (
    NMRFormatError,
    NMRFormatOptions,
    format_nmr_spectrum,
)
from chem_workflow.spectroscopy.nmr.parsing import (
    NMRInputError,
    parse_mestrenova_multiplet_table,
    parse_shift_list,
)

nmr_app = typer.Typer(help="NMR peak list 相关命令", no_args_is_help=True)

@nmr_app.command("parse")
def nmr_parse(
    path: Path | None = typer.Argument(
        None,
        help="MestReNova multiplet 表文件路径（tab-separated）",
        exists=False,
    ),
    inline: str | None = typer.Option(
        None, "--inline", "-i", help="直接贴 multiplet 表文本，与 path 二选一"
    ),
    nucleus: str = typer.Option("1H", "--nucleus", "-n", help="核种：1H / 13C / 19F / 31P"),
    frequency: float | None = typer.Option(
        None, "--frequency", "-f", help="谱仪频率 (MHz)，例如 400"
    ),
    solvent: str | None = typer.Option(None, "--solvent", help="溶剂，例如 CDCl3 / DMSO-d6"),
    sample_id: str | None = typer.Option(None, "--sample-id", help="样品编号"),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出"),
    out: Path | None = typer.Option(None, "--out", "-o", help="输出 JSON 到文件（隐含 --json）"),
) -> None:
    """解析 MestReNova multiplet 表（tab-separated），输出结构化 peak list。"""
    if (path is None) == (inline is None):
        raise typer.BadParameter("请提供 path 或 --inline 二者之一")
    if nucleus not in ("1H", "13C", "19F", "31P"):
        raise typer.BadParameter(f"--nucleus 必须是 1H/13C/19F/31P，收到 {nucleus!r}")

    source: str | Path = path if path is not None else inline  # type: ignore[assignment]
    try:
        spectrum = parse_mestrenova_multiplet_table(
            source,
            nucleus=nucleus,  # type: ignore[arg-type]
            frequency_mhz=frequency,
            solvent=solvent,
            sample_id=sample_id,
        )
    except NMRInputError as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    payload = spectrum.model_dump_json(indent=2)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"已写入 {out}")
        return
    if as_json:
        typer.echo(payload)
    else:
        _print_spectrum_human(spectrum)

@nmr_app.command("format")
def nmr_format(
    path: Path | None = typer.Argument(
        None,
        help="MestReNova multiplet 表文件路径（tab-separated）",
        exists=False,
    ),
    inline: str | None = typer.Option(
        None, "--inline", "-i", help="直接贴 multiplet 表文本，与 path 二选一"
    ),
    nucleus: str = typer.Option("1H", "--nucleus", "-n", help="核种：1H / 13C"),
    frequency: float | None = typer.Option(
        None, "--frequency", "-f", help="谱仪频率 (MHz)，例如 400"
    ),
    solvent: str | None = typer.Option(None, "--solvent", help="溶剂，例如 CDCl3 / DMSO-d6"),
    sample_id: str | None = typer.Option(None, "--sample-id", help="样品编号"),
    include_assignment: bool = typer.Option(
        False,
        "--include-assignment",
        help="在输出中保留 assignment；默认关闭，因为 MestReNova 字母 ID 通常不适合论文正文",
    ),
    sort_descending: bool = typer.Option(
        True,
        "--sort/--preserve-order",
        help="按化学位移从高到低排序；--preserve-order 保留输入顺序",
    ),
    show_solvent: bool = typer.Option(
        True,
        "--show-solvent/--hide-solvent",
        help="是否在 NMR header 中显示溶剂",
    ),
    show_frequency: bool = typer.Option(
        True,
        "--show-frequency/--hide-frequency",
        help="是否在 NMR header 中显示频率",
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help="输出格式化 NMR 文本到文件"),
) -> None:
    """把 MestReNova multiplet 表格式化为常见实验记录 / SI 风格 NMR 描述。"""
    if (path is None) == (inline is None):
        raise typer.BadParameter("请提供 path 或 --inline 二者之一")
    if nucleus not in ("1H", "13C"):
        raise typer.BadParameter(f"--nucleus 当前只支持 1H/13C，收到 {nucleus!r}")

    source: str | Path = path if path is not None else inline  # type: ignore[assignment]
    try:
        spectrum = parse_mestrenova_multiplet_table(
            source,
            nucleus=nucleus,  # type: ignore[arg-type]
            frequency_mhz=frequency,
            solvent=solvent,
            sample_id=sample_id,
        )
        text = format_nmr_spectrum(
            spectrum,
            NMRFormatOptions(
                include_assignment=include_assignment,
                sort_descending=sort_descending,
                include_solvent=show_solvent,
                include_frequency=show_frequency,
            ),
        )
    except (NMRInputError, NMRFormatError) as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        typer.echo(f"已写入 {out}")
        return
    typer.echo(text)

@nmr_app.command("assign")
def nmr_assign(
    path: Path | None = typer.Argument(
        None,
        help="MestReNova multiplet 表文件路径（tab/CSV/semicolon separated）",
        exists=False,
    ),
    inline: str | None = typer.Option(
        None, "--inline", "-i", help="直接贴 multiplet 表文本，与 path 二选一"
    ),
    nucleus: str = typer.Option("1H", "--nucleus", "-n", help="核种：1H 或 13C"),
    smiles: str | None = typer.Option(
        None, "--smiles", "-s", help="目标化合物 SMILES，与 --structure 二选一"
    ),
    structure: Path | None = typer.Option(
        None,
        "--structure",
        help="结构文件路径（.cdx/.cdxml/.mol/.sdf/.smi/.smiles），与 --smiles 二选一",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    frequency: float | None = typer.Option(
        None, "--frequency", "-f", help="谱仪频率 (MHz)，例如 400"
    ),
    solvent: str | None = typer.Option(None, "--solvent", help="溶剂，例如 CDCl3 / DMSO-d6"),
    sample_id: str | None = typer.Option(None, "--sample-id", help="样品编号"),
    rules: Path | None = typer.Option(
        None,
        "--rules",
        help="自定义 assignment 规则 YAML；默认按核种选 nmr_1h_rules / nmr_13c_rules",
        exists=False,
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help="输出 Markdown 草稿到文件"),
) -> None:
    """生成 1H / 13C NMR 候选 assignment 草稿；不会给出唯一自动定论。"""
    if (path is None) == (inline is None):
        raise typer.BadParameter("请提供 path 或 --inline 二者之一")
    if (smiles is None) == (structure is None):
        raise typer.BadParameter("请提供 --smiles 或 --structure 二者之一")
    if nucleus not in ("1H", "13C"):
        raise typer.BadParameter("--nucleus 必须是 1H 或 13C")

    source: str | Path = path if path is not None else inline  # type: ignore[assignment]
    try:
        mol = parse_smiles(smiles) if smiles is not None else load_structure(structure)
        if nucleus == "1H":
            spectrum = parse_mestrenova_multiplet_table(
                source,
                nucleus=nucleus,
                frequency_mhz=frequency,
                solvent=solvent,
                sample_id=sample_id,
            )
        else:
            spectrum = parse_shift_list(
                source,
                nucleus=nucleus,
                frequency_mhz=frequency,
                solvent=solvent,
                sample_id=sample_id,
            )
        assignment_rules = load_assignment_rules(rules) if rules is not None else None
        draft = assign_nmr(mol, spectrum, rules=assignment_rules)
        markdown = render_assignment_draft(draft)
    except (AssignmentError, NMRInputError, StructureInputError, ConsistencyError) as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        typer.echo(f"已写入 {out}")
        return
    typer.echo(markdown, nl=False)

@nmr_app.command("check")
def nmr_check(
    path: Path | None = typer.Argument(
        None,
        help="NMR peak list 文件路径（tab/CSV/semicolon separated）",
        exists=False,
    ),
    inline: str | None = typer.Option(
        None, "--inline", "-i", help="直接贴 peak 表文本，与 path 二选一"
    ),
    nucleus: str = typer.Option("13C", "--nucleus", "-n", help="核种：1H / 13C / 19F / 31P"),
    smiles: str | None = typer.Option(
        None, "--smiles", "-s", help="目标化合物 SMILES，与 --structure 二选一"
    ),
    structure: Path | None = typer.Option(
        None,
        "--structure",
        help="结构文件路径，与 --smiles 二选一",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
) -> None:
    """对比结构理论唯一信号数与实测峰数（对得上/对不上的快速判断）。"""
    if (path is None) == (inline is None):
        raise typer.BadParameter("请提供 path 或 --inline 二者之一")
    if (smiles is None) == (structure is None):
        raise typer.BadParameter("请提供 --smiles 或 --structure 二者之一")
    if nucleus not in ("1H", "13C", "19F", "31P"):
        raise typer.BadParameter("--nucleus 必须是 1H / 13C / 19F / 31P")

    source: str | Path = path if path is not None else inline  # type: ignore[assignment]
    try:
        mol = parse_smiles(smiles) if smiles is not None else load_structure(structure)
        if nucleus == "1H":
            spectrum = parse_mestrenova_multiplet_table(source, nucleus=nucleus)
        else:
            spectrum = parse_shift_list(source, nucleus=nucleus)
        check = check_signal_count(mol, spectrum)
    except (NMRInputError, StructureInputError, ConsistencyError) as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    color = typer.colors.GREEN if check.verdict == "match" else typer.colors.YELLOW
    typer.secho(check.message, fg=color)

def _print_spectrum_human(spectrum) -> None:  # noqa: ANN001 — local helper
    head = f"{spectrum.nucleus} NMR"
    if spectrum.frequency_mhz:
        head += f" ({spectrum.frequency_mhz:g} MHz"
        if spectrum.solvent:
            head += f", {spectrum.solvent}"
        head += ")"
    elif spectrum.solvent:
        head += f" ({spectrum.solvent})"
    typer.echo(head)
    typer.echo(f"{'δ (ppm)':>9} {'mult':>6} {'H':>5}  J (Hz)")
    for p in spectrum.peaks:
        j = ", ".join(f"{v:g}" for v in p.j_hz) if p.j_hz else ""
        h = f"{p.integration:g}" if p.integration is not None else ""
        typer.echo(f"{p.shift_ppm:>9.3f} {p.multiplicity or '':>6} {h:>5}  {j}")

__all__ = ["nmr_app", "nmr_assign", "nmr_check", "nmr_format", "nmr_parse"]

