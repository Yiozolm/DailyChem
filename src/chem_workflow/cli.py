"""chemwf 命令行入口。"""

from __future__ import annotations

import typer

from chem_workflow import __version__

app = typer.Typer(help="化学工作流自动化工具 (chemwf)", no_args_is_help=True)


@app.callback()
def _root() -> None:
    """chemwf 根命令。"""


@app.command()
def version() -> None:
    """打印版本号。"""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
