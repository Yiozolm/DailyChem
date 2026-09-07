"""Experiment-record CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import typer

from chem_workflow.records import (
    Language,
    RecordInputError,
    load_reaction_record,
    render_experiment_record,
    write_experiment_record,
)

records_app = typer.Typer(help="实验记录相关命令", no_args_is_help=True)

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

__all__ = ["records_app", "records_generate"]

