"""Root Typer application and sub-command registration."""

from __future__ import annotations

import typer

from chem_workflow import __version__
from chem_workflow.core.logging import configure_logging
from chem_workflow.interfaces.cli.ai import llm_app
from chem_workflow.interfaces.cli.archive import archive_app
from chem_workflow.interfaces.cli.config import config_app
from chem_workflow.interfaces.cli.history import db_app, lit_app
from chem_workflow.interfaces.cli.nmr import nmr_app
from chem_workflow.interfaces.cli.ocr import ocr_app
from chem_workflow.interfaces.cli.records import records_app
from chem_workflow.interfaces.cli.spectra import ir_app, ms_app, uv_app
from chem_workflow.interfaces.cli.structure import structure_app

app = typer.Typer(help="化学工作流自动化工具 (chemwf)", no_args_is_help=True)

@app.callback()
def _root() -> None:
    """chemwf 根命令。"""
    configure_logging()

@app.command()
def version() -> None:
    """打印版本号。"""
    typer.echo(__version__)

app.add_typer(archive_app)
app.add_typer(structure_app, name="structure")
app.add_typer(nmr_app, name="nmr")
app.add_typer(ocr_app, name="ocr")
app.add_typer(records_app, name="records")
app.add_typer(llm_app, name="llm")
app.add_typer(ms_app, name="ms")
app.add_typer(ir_app, name="ir")
app.add_typer(uv_app, name="uv")
app.add_typer(db_app, name="db")
app.add_typer(lit_app, name="lit")
app.add_typer(config_app, name="config")

__all__ = ["app", "version"]
