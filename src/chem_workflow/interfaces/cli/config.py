"""Typer commands for ``.chemwf.toml`` configuration."""

from __future__ import annotations

from pathlib import Path

import typer

from chem_workflow.core.config import (
    CONFIG_FILENAME,
    CONFIG_TEMPLATE,
    ConfigError,
    find_config_path,
    load_config,
)

config_app = typer.Typer(help="chemwf 配置文件管理", no_args_is_help=True)


@config_app.command("show")
def config_show(
    path: Path | None = typer.Option(None, "--path", help="指定配置文件；默认就近查找"),
) -> None:
    """打印当前生效的配置（含来源）。"""
    try:
        config = load_config(path)
    except ConfigError as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e
    source = path or find_config_path() or "（内置默认值）"
    typer.echo(f"# 配置来源：{source}")
    typer.echo(config.model_dump_json(indent=2))


@config_app.command("init")
def config_init(
    project_dir: Path = typer.Option(Path("."), "--project-dir", "-p", help="写入目录"),
    overwrite: bool = typer.Option(False, "--overwrite", help="覆盖已有配置文件"),
) -> None:
    """在指定目录写一份带注释的 .chemwf.toml 模板。"""
    target = project_dir / CONFIG_FILENAME
    if target.exists() and not overwrite:
        typer.secho(
            f"配置文件已存在：{target}。如需覆盖请加 --overwrite。",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    typer.echo(f"已写入 {target}")


__all__ = ["config_app", "config_init", "config_show"]
