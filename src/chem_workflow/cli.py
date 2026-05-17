"""chemwf 命令行入口。"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from chem_workflow import __version__
from chem_workflow.structure import (
    StructureInputError,
    load_structure,
    mol_info,
    parse_smiles,
)

app = typer.Typer(help="化学工作流自动化工具 (chemwf)", no_args_is_help=True)

structure_app = typer.Typer(help="化合物结构相关命令", no_args_is_help=True)
app.add_typer(structure_app, name="structure")


@app.callback()
def _root() -> None:
    """chemwf 根命令。"""


@app.command()
def version() -> None:
    """打印版本号。"""
    typer.echo(__version__)


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
    as_json: bool = typer.Option(
        False, "--json", help="以 JSON 输出而非键值表"
    ),
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


if __name__ == "__main__":
    app()
