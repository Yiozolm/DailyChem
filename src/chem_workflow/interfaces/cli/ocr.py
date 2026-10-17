"""CLI diagnostics and lifecycle controls for the local GLM-OCR service."""

from __future__ import annotations

import typer

from chem_workflow.core.config import ConfigError, load_config
from chem_workflow.ocr import OCRRuntimeError, OCRRuntimeManager

ocr_app = typer.Typer(help="本地 WSL2 + vLLM + GLM-OCR 管理", no_args_is_help=True)


def _manager() -> OCRRuntimeManager:
    try:
        return OCRRuntimeManager(load_config().ocr)
    except ConfigError as error:
        typer.secho(f"错误: {error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from error


@ocr_app.command("doctor")
def doctor() -> None:
    """检查 WSL2、配置和本地 OCR 服务前置条件。"""
    manager = _manager()
    problems = manager.doctor()
    if problems:
        typer.secho("本地 OCR 检查未通过：", fg=typer.colors.RED, err=True)
        for problem in problems:
            typer.echo(f"- {problem}", err=True)
        raise typer.Exit(code=1)
    typer.echo("本地 OCR 前置条件看起来正常。")


@ocr_app.command("status")
def status() -> None:
    """显示本地 OCR 服务状态。"""
    typer.echo(_manager().status().model_dump_json(indent=2))


@ocr_app.command("start")
def start() -> None:
    """按需启动 WSL 内的 vLLM OCR 服务。"""
    try:
        result = _manager().start()
    except OCRRuntimeError as error:
        typer.secho(f"错误: {error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from error
    typer.echo(result.model_dump_json(indent=2))


@ocr_app.command("stop")
def stop() -> None:
    """停止 WSL 内的 vLLM OCR 服务。"""
    _manager().stop()
    typer.echo("已请求停止本地 OCR 服务。")


__all__ = ["doctor", "ocr_app", "start", "status", "stop"]
