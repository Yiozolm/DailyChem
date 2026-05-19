"""chemwf 命令行入口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import typer

from chem_workflow import __version__
from chem_workflow.assignment import (
    AssignmentError,
    assign_1h_nmr,
    load_assignment_rules,
    render_assignment_draft,
)
from chem_workflow.llm_cli import llm_app
from chem_workflow.nmr import (
    NMRInputError,
    parse_mestrenova_multiplet_table,
)
from chem_workflow.nmr_formatter import (
    NMRFormatError,
    NMRFormatOptions,
    format_nmr_spectrum,
)
from chem_workflow.records import (
    Language,
    RecordInputError,
    load_reaction_record,
    render_experiment_record,
    write_experiment_record,
)
from chem_workflow.storage import (
    RawFileGroup,
    StorageError,
    init_compound_archive,
)
from chem_workflow.structure import (
    StructureInputError,
    draw_structure,
    load_structure,
    mol_info,
    parse_smiles,
)

app = typer.Typer(help="化学工作流自动化工具 (chemwf)", no_args_is_help=True)

structure_app = typer.Typer(help="化合物结构相关命令", no_args_is_help=True)
app.add_typer(structure_app, name="structure")

nmr_app = typer.Typer(help="NMR peak list 相关命令", no_args_is_help=True)
app.add_typer(nmr_app, name="nmr")

records_app = typer.Typer(help="实验记录相关命令", no_args_is_help=True)
app.add_typer(records_app, name="records")

app.add_typer(llm_app, name="llm")


@app.callback()
def _root() -> None:
    """chemwf 根命令。"""


@app.command()
def version() -> None:
    """打印版本号。"""
    typer.echo(__version__)


@app.command("init-compound")
def init_compound(
    compound_id: str = typer.Option(..., "--id", help="化合物 ID，例如 C001"),
    project_dir: Path = typer.Option(
        Path("."),
        "--project-dir",
        "-p",
        help="项目归档根目录；会在其中创建 compounds/<id>/",
    ),
    smiles: str | None = typer.Option(
        None, "--smiles", "-s", help="直接传 SMILES 字符串，与 --structure 二选一"
    ),
    structure: Path | None = typer.Option(
        None,
        "--structure",
        help="结构文件路径（.cdx/.cdxml/.mol/.sdf/.smi/.smiles），与 --smiles 二选一",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    copy_nmr_1h: list[Path] | None = typer.Option(
        None,
        "--copy-nmr-1h",
        help="复制 1H NMR 原始/导出文件到 nmr/1H/raw/；可重复传",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    copy_nmr_13c: list[Path] | None = typer.Option(
        None,
        "--copy-nmr-13c",
        help="复制 13C NMR 原始/导出文件到 nmr/13C/raw/；可重复传",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    copy_ms: list[Path] | None = typer.Option(
        None,
        "--copy-ms",
        help="复制 MS/HRMS 原始/导出文件到 ms/raw/；可重复传",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    copy_ir: list[Path] | None = typer.Option(
        None,
        "--copy-ir",
        help="复制 IR 原始/导出文件到 ir/raw/；可重复传",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    copy_record: list[Path] | None = typer.Option(
        None,
        "--copy-record",
        help="复制实验记录文件到 records/；可重复传",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="允许覆盖自动生成/复制的文件"),
) -> None:
    """初始化标准化 compound 归档文件夹，并生成 metadata / summary。"""
    raw_groups = _build_raw_file_groups(
        copy_nmr_1h=copy_nmr_1h,
        copy_nmr_13c=copy_nmr_13c,
        copy_ms=copy_ms,
        copy_ir=copy_ir,
        copy_record=copy_record,
    )
    try:
        result = init_compound_archive(
            compound_id=compound_id,
            project_dir=project_dir,
            smiles=smiles,
            structure_path=structure,
            raw_file_groups=raw_groups,
            overwrite=overwrite,
        )
    except (StorageError, StructureInputError) as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    typer.echo(f"已初始化 {result.compound_dir}")
    typer.echo(f"metadata: {result.metadata_path}")
    typer.echo(f"summary:  {result.summary_path}")
    if result.copied_raw_files:
        typer.echo(f"copied:   {len(result.copied_raw_files)} file(s)")


@structure_app.command("parse")
def structure_parse(
    path: Path | None = typer.Argument(
        None,
        help="结构文件路径（.cdx/.cdxml/.mol/.sdf/.smi/.smiles）",
        exists=False,
    ),
    smiles: str | None = typer.Option(
        None, "--smiles", "-s", help="直接传 SMILES 字符串，与 path 二选一"
    ),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 输出而非键值表"),
) -> None:
    """解析结构文件或 SMILES，打印 canonical SMILES、分子式、分子量、原子数。"""
    if (path is None) == (smiles is None):
        raise typer.BadParameter("请提供 path 或 --smiles 二者之一")

    try:
        mol = parse_smiles(smiles) if smiles is not None else load_structure(path)
    except StructureInputError as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    info = mol_info(mol)
    if as_json:
        typer.echo(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        for key, value in info.items():
            typer.echo(f"{key:12s}  {value}")


def _parse_size(value: str) -> tuple[int, int]:
    try:
        w, h = (int(part) for part in value.lower().split("x", 1))
    except (ValueError, AttributeError) as e:
        raise typer.BadParameter(f"--size 必须形如 500x500，得到 {value!r}") from e
    if w <= 0 or h <= 0:
        raise typer.BadParameter("--size 宽高必须为正整数")
    return w, h


@structure_app.command("draw")
def structure_draw(
    path: Path | None = typer.Argument(
        None,
        help="结构文件路径（.cdx/.cdxml/.mol/.sdf/.smi/.smiles）",
        exists=False,
    ),
    smiles: str | None = typer.Option(
        None, "--smiles", "-s", help="直接传 SMILES 字符串，与 path 二选一"
    ),
    out: Path = typer.Option(
        ..., "--out", "-o", help="输出图片路径，按后缀决定格式（.svg / .png）"
    ),
    atom_index: bool = typer.Option(
        False, "--atom-index", help="叠加 RDKit 0-based 原子编号（assignment 辅助用）"
    ),
    size: str = typer.Option("500x500", "--size", help="图片尺寸，格式 宽x高，例如 800x600"),
) -> None:
    """把结构渲染成 SVG 或 PNG，可叠加原子编号。"""
    if (path is None) == (smiles is None):
        raise typer.BadParameter("请提供 path 或 --smiles 二者之一")
    size_tuple = _parse_size(size)
    try:
        mol = parse_smiles(smiles) if smiles is not None else load_structure(path)
        written = draw_structure(mol, out, show_atom_index=atom_index, size=size_tuple)
    except StructureInputError as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"已写入 {written}")


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
        None, "--inline", "-i", help="直接贴 1H multiplet 表文本，与 path 二选一"
    ),
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
        help="自定义 1H assignment 规则 YAML；默认 data/rules/nmr_1h_rules.yaml",
        exists=False,
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help="输出 Markdown 草稿到文件"),
) -> None:
    """生成 1H NMR 候选 assignment 草稿；不会给出唯一自动定论。"""
    if (path is None) == (inline is None):
        raise typer.BadParameter("请提供 path 或 --inline 二者之一")
    if (smiles is None) == (structure is None):
        raise typer.BadParameter("请提供 --smiles 或 --structure 二者之一")

    source: str | Path = path if path is not None else inline  # type: ignore[assignment]
    try:
        mol = parse_smiles(smiles) if smiles is not None else load_structure(structure)
        spectrum = parse_mestrenova_multiplet_table(
            source,
            nucleus="1H",
            frequency_mhz=frequency,
            solvent=solvent,
            sample_id=sample_id,
        )
        draft = assign_1h_nmr(
            mol,
            spectrum,
            rules=load_assignment_rules(rules) if rules is not None else None,
        )
        markdown = render_assignment_draft(draft)
    except (AssignmentError, NMRInputError, StructureInputError) as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        typer.echo(f"已写入 {out}")
        return
    typer.echo(markdown, nl=False)


@records_app.command("generate")
def records_generate(
    input_path: Path = typer.Argument(
        ...,
        help="实验记录结构化输入（.yaml / .yml / .json）",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    language: str = typer.Option("en", "--language", "-l", help="输出语言：en / zh"),
    out: Path | None = typer.Option(None, "--out", "-o", help="输出 Markdown 文件路径"),
) -> None:
    """根据结构化 YAML/JSON 生成实验记录 Markdown 初稿。"""
    record_language = _parse_record_language(language)

    try:
        record = load_reaction_record(input_path)
        if out is None:
            typer.echo(render_experiment_record(record, record_language))
        else:
            written = write_experiment_record(record, out, record_language)
            typer.echo(f"已写入 {written}")
    except RecordInputError as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e


def _parse_record_language(value: str) -> Language:
    if value not in ("en", "zh"):
        raise typer.BadParameter(f"--language 必须是 en/zh，收到 {value!r}")
    return cast(Language, value)


def _build_raw_file_groups(
    *,
    copy_nmr_1h: list[Path] | None,
    copy_nmr_13c: list[Path] | None,
    copy_ms: list[Path] | None,
    copy_ir: list[Path] | None,
    copy_record: list[Path] | None,
) -> tuple[RawFileGroup, ...]:
    specs = [
        ("1H NMR", Path("nmr/1H/raw"), copy_nmr_1h),
        ("13C NMR", Path("nmr/13C/raw"), copy_nmr_13c),
        ("MS", Path("ms/raw"), copy_ms),
        ("IR", Path("ir/raw"), copy_ir),
        ("record", Path("records"), copy_record),
    ]
    return tuple(
        RawFileGroup(label=label, destination=destination, sources=tuple(paths))
        for label, destination, paths in specs
        if paths
    )


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


if __name__ == "__main__":
    app()
