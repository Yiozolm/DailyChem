"""Typer commands for local compound and literature history."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import typer

from chem_workflow.history import (
    DEFAULT_DB_PATH,
    DatabaseError,
    all_compounds,
    all_literature,
    connect,
    get_compound,
    make_literature_record,
    make_record,
    scan_archive,
    upsert_compound,
    upsert_literature,
)
from chem_workflow.history.search import SearchError, similarity_search, substructure_search

db_app = typer.Typer(help="本地历史数据库与检索命令", no_args_is_help=True)
lit_app = typer.Typer(help="本地文献参考与检索命令", no_args_is_help=True)


@db_app.command("add")
def db_add(
    compound_id: str = typer.Option(..., "--id", help="化合物 ID，例如 C001"),
    smiles: str = typer.Option(..., "--smiles", "-s", help="化合物 SMILES"),
    source_dir: str | None = typer.Option(None, "--source-dir", help="来源目录（可选）"),
    h1: str | None = typer.Option(None, "--h1", help="1H NMR 文本"),
    c13: str | None = typer.Option(None, "--c13", help="13C NMR 文本"),
    hrms: str | None = typer.Option(None, "--hrms", help="HRMS 文本"),
    ir: str | None = typer.Option(None, "--ir", help="IR 文本"),
    uv: str | None = typer.Option(None, "--uv", help="UV-vis 文本"),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite 数据库路径"),
) -> None:
    """把单个化合物（及可选谱学文本）加入本地历史库。"""
    spectra = {"1H": h1, "13C": c13, "HRMS": hrms, "IR": ir, "UV": uv}
    try:
        record = make_record(
            compound_id=compound_id,
            smiles=smiles,
            source_dir=source_dir,
            spectra={k: v for k, v in spectra.items() if v},
        )
        with closing(connect(db)) as conn:
            upsert_compound(conn, record)
    except DatabaseError as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"已写入 {record.compound_id}（{record.formula}, MW {record.molecular_weight}）")


@db_app.command("import")
def db_import(
    project_dir: Path = typer.Option(Path("."), "--project-dir", "-p", help="归档项目根目录"),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite 数据库路径"),
) -> None:
    """扫描 compounds/*/metadata.json 批量导入本地历史库。"""
    try:
        records = scan_archive(project_dir)
        with closing(connect(db)) as conn:
            for record in records:
                upsert_compound(conn, record)
    except DatabaseError as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"已导入 {len(records)} 个化合物到 {db}")


@db_app.command("list")
def db_list(db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite 数据库路径")) -> None:
    """列出本地历史库中的所有化合物。"""
    with closing(connect(db)) as conn:
        records = all_compounds(conn)
    if not records:
        typer.echo("（数据库为空）")
        return
    for record in records:
        mw = f"{record.molecular_weight:.2f}" if record.molecular_weight is not None else "-"
        typer.echo(
            f"{record.compound_id:12s}  {record.formula or '-':14s}  MW {mw}  {record.smiles}"
        )


@db_app.command("get")
def db_get(
    compound_id: str = typer.Argument(..., help="化合物 ID"),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite 数据库路径"),
) -> None:
    """显示某化合物的详情（含谱学文本）。"""
    with closing(connect(db)) as conn:
        record = get_compound(conn, compound_id)
    if record is None:
        typer.secho(f"未找到化合物：{compound_id}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=1)
    typer.echo(record.model_dump_json(indent=2))


@db_app.command("search")
def db_search(
    smiles: str = typer.Option(..., "--smiles", "-s", help="查询 SMILES 或 SMARTS"),
    substructure: bool = typer.Option(False, "--substructure", help="子结构搜索"),
    similarity: bool = typer.Option(False, "--similarity", help="相似度搜索（Tanimoto）"),
    threshold: float = typer.Option(0.7, "--threshold", help="相似度阈值（0–1）"),
    top_k: int = typer.Option(10, "--top-k", help="相似度最多返回条数"),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite 数据库路径"),
) -> None:
    """在本地历史库中按子结构或相似度检索化合物。"""
    if substructure == similarity:
        typer.secho(
            "错误: 请二选一：--substructure 或 --similarity。", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)

    try:
        with closing(connect(db)) as conn:
            records = all_compounds(conn)
        hits = (
            substructure_search(records, smiles)
            if substructure
            else similarity_search(records, smiles, threshold=threshold, top_k=top_k)
        )
    except (DatabaseError, SearchError) as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    if not hits:
        typer.echo("（无匹配）")
        return
    for hit in hits:
        score = f"  score {hit.score:.3f}" if hit.score is not None else ""
        typer.echo(
            f"{hit.compound.compound_id:12s}  {hit.compound.formula or '-':14s}  "
            f"{hit.compound.smiles}{score}"
        )


@lit_app.command("add")
def lit_add(
    doi: str = typer.Option(..., "--doi", help="文献 DOI（唯一键）"),
    smiles: str = typer.Option(..., "--smiles", "-s", help="文献化合物 SMILES"),
    title: str | None = typer.Option(None, "--title", help="文献标题"),
    authors: str | None = typer.Option(None, "--authors", help="作者"),
    year: int | None = typer.Option(None, "--year", help="年份"),
    h1: str | None = typer.Option(None, "--h1", help="文献 1H NMR 文本"),
    c13: str | None = typer.Option(None, "--c13", help="文献 13C NMR 文本"),
    note: str | None = typer.Option(None, "--note", help="备注"),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite 数据库路径"),
) -> None:
    """把一条文献参考（含可选 NMR 文本）加入本地库。"""
    try:
        record = make_literature_record(
            doi=doi,
            smiles=smiles,
            title=title,
            authors=authors,
            year=year,
            nmr_1h=h1,
            nmr_13c=c13,
            note=note,
        )
        with closing(connect(db)) as conn:
            upsert_literature(conn, record)
    except DatabaseError as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"已写入文献 {record.doi}（{record.smiles}）")


@lit_app.command("list")
def lit_list(db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite 数据库路径")) -> None:
    """列出本地库中的所有文献参考。"""
    with closing(connect(db)) as conn:
        records = all_literature(conn)
    if not records:
        typer.echo("（无文献）")
        return
    for record in records:
        typer.echo(
            f"{record.doi:28s}  {record.year or '----'}  "
            f"{record.title or '-'}  {record.smiles}"
        )


@lit_app.command("search")
def lit_search(
    smiles: str = typer.Option(..., "--smiles", "-s", help="查询 SMILES 或 SMARTS"),
    substructure: bool = typer.Option(False, "--substructure", help="子结构搜索"),
    similarity: bool = typer.Option(False, "--similarity", help="相似度搜索（Tanimoto）"),
    threshold: float = typer.Option(0.7, "--threshold", help="相似度阈值（0–1）"),
    top_k: int = typer.Option(10, "--top-k", help="相似度最多返回条数"),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite 数据库路径"),
) -> None:
    """在文献库中按子结构或相似度检索。"""
    if substructure == similarity:
        typer.secho(
            "错误: 请二选一：--substructure 或 --similarity。", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)
    try:
        with closing(connect(db)) as conn:
            records = all_literature(conn)
        hits = (
            substructure_search(records, smiles)
            if substructure
            else similarity_search(records, smiles, threshold=threshold, top_k=top_k)
        )
    except (DatabaseError, SearchError) as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    if not hits:
        typer.echo("（无匹配）")
        return
    for hit in hits:
        score = f"  score {hit.score:.3f}" if hit.score is not None else ""
        typer.echo(f"{hit.record.doi:28s}  {hit.record.title or '-'}  {hit.record.smiles}{score}")


@lit_app.command("compare")
def lit_compare(
    smiles: str = typer.Option(..., "--smiles", "-s", help="当前化合物 SMILES"),
    threshold: float = typer.Option(0.4, "--threshold", help="相似度阈值（0–1）"),
    top_k: int = typer.Option(5, "--top-k", help="最多返回条数"),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite 数据库路径"),
) -> None:
    """按相似度列出文献命中及其报道的 NMR 文本，供人工对照当前化合物。"""
    try:
        with closing(connect(db)) as conn:
            records = all_literature(conn)
        hits = similarity_search(records, smiles, threshold=threshold, top_k=top_k)
    except (DatabaseError, SearchError) as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e

    if not hits:
        typer.echo("（无相似文献）")
        return
    for hit in hits:
        lit = hit.record
        typer.echo(f"## {lit.doi}  (similarity {hit.score:.3f})")
        if lit.title:
            typer.echo(f"   {lit.title}")
        if lit.nmr_1h:
            typer.echo(f"   1H:  {lit.nmr_1h}")
        if lit.nmr_13c:
            typer.echo(f"   13C: {lit.nmr_13c}")


__all__ = [
    "db_add",
    "db_app",
    "db_get",
    "db_import",
    "db_list",
    "db_search",
    "lit_add",
    "lit_app",
    "lit_compare",
    "lit_list",
    "lit_search",
]
