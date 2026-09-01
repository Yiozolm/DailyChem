"""Top-level archive and backup CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from chem_workflow.archive import (
    RawFileGroup,
    StorageError,
    backup_compound_archive,
    init_compound_archive,
)
from chem_workflow.compounds.structure import StructureInputError

archive_app = typer.Typer()

@archive_app.command("backup")
def backup(
    compound_id: str = typer.Option(..., "--id", help="要备份的化合物 ID"),
    project_dir: Path = typer.Option(
        Path("."), "--project-dir", "-p", help="项目归档根目录（含 compounds/）"
    ),
    backup_root: Path | None = typer.Option(
        None, "--backup-root", help="备份输出目录；默认 <project-dir>/backups/"
    ),
) -> None:
    """把某 compound 的归档文件夹打包成 zip 备份（只读源，不覆盖原始数据）。"""
    try:
        created = backup_compound_archive(
            compound_id=compound_id,
            project_dir=project_dir,
            backup_root=backup_root,
        )
    except StorageError as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"已备份到 {created}")

@archive_app.command("init-compound")
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

__all__ = ["archive_app", "backup", "init_compound"]

