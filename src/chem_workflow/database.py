"""Phase 11 local history database (SQLite) for compounds and their spectra.

Stores compounds done in the lab so they can be searched later by ID / SMILES / substructure /
similarity (see :mod:`chem_workflow.search`). Fingerprints are not persisted; structure search
recomputes them on demand from the stored canonical SMILES, which keeps the schema simple and
robust across RDKit versions for the local scale this tool targets.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import typer
from pydantic import BaseModel, Field

from chem_workflow.structure import StructureInputError, parse_smiles

DEFAULT_DB_PATH = Path("data/chem_workflow.sqlite")
SPECTRUM_KINDS = ("1H", "13C", "HRMS", "MS", "IR", "UV")


class DatabaseError(ValueError):
    """本地历史数据库读写失败时抛出。错误信息会展示给用户，应包含可操作建议。"""


class CompoundRecord(BaseModel):
    """A compound plus its characterization texts, as stored in the history database."""

    compound_id: str
    smiles: str  # canonical
    formula: str | None = None
    molecular_weight: float | None = None
    source_dir: str | None = None
    created_at: str | None = None
    spectra: dict[str, str] = Field(default_factory=dict)  # {"1H": "...", "HRMS": "...", ...}


class LiteratureRecord(BaseModel):
    """A literature reference plus its reported NMR data, keyed by DOI."""

    doi: str
    smiles: str  # canonical
    title: str | None = None
    authors: str | None = None
    year: int | None = None
    nmr_1h: str | None = None
    nmr_13c: str | None = None
    note: str | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS compounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compound_id TEXT UNIQUE NOT NULL,
    smiles TEXT NOT NULL,
    formula TEXT,
    molecular_weight REAL,
    source_dir TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS spectra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compound_pk INTEGER NOT NULL REFERENCES compounds(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spectra_compound ON spectra(compound_pk);
CREATE TABLE IF NOT EXISTS literature (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doi TEXT UNIQUE NOT NULL,
    title TEXT,
    authors TEXT,
    year INTEGER,
    smiles TEXT NOT NULL,
    nmr_1h TEXT,
    nmr_13c TEXT,
    note TEXT
);
"""


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open (creating if needed) the history database and ensure the schema exists."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    return conn


def upsert_compound(conn: sqlite3.Connection, record: CompoundRecord) -> None:
    """Insert or replace a compound and its spectra, keyed by ``compound_id`` (idempotent)."""
    compound_id = record.compound_id.strip()
    if not compound_id:
        raise DatabaseError("compound_id 不能为空。")
    if not record.smiles.strip():
        raise DatabaseError("smiles 不能为空。")

    with conn:
        conn.execute(
            """
            INSERT INTO compounds (compound_id, smiles, formula, molecular_weight,
                                   source_dir, created_at)
            VALUES (:compound_id, :smiles, :formula, :molecular_weight, :source_dir, :created_at)
            ON CONFLICT(compound_id) DO UPDATE SET
                smiles = excluded.smiles,
                formula = excluded.formula,
                molecular_weight = excluded.molecular_weight,
                source_dir = excluded.source_dir,
                created_at = excluded.created_at
            """,
            {
                "compound_id": compound_id,
                "smiles": record.smiles.strip(),
                "formula": record.formula,
                "molecular_weight": record.molecular_weight,
                "source_dir": record.source_dir,
                "created_at": record.created_at,
            },
        )
        row = conn.execute(
            "SELECT id FROM compounds WHERE compound_id = ?", (compound_id,)
        ).fetchone()
        compound_pk = int(row["id"])
        conn.execute("DELETE FROM spectra WHERE compound_pk = ?", (compound_pk,))
        conn.executemany(
            "INSERT INTO spectra (compound_pk, kind, text) VALUES (?, ?, ?)",
            [(compound_pk, kind, text) for kind, text in record.spectra.items() if text.strip()],
        )


def get_compound(conn: sqlite3.Connection, compound_id: str) -> CompoundRecord | None:
    """Return the compound with this exact ``compound_id``, or None."""
    row = conn.execute(
        "SELECT * FROM compounds WHERE compound_id = ?", (compound_id.strip(),)
    ).fetchone()
    if row is None:
        return None
    return _row_to_record(conn, row)


def find_by_smiles(conn: sqlite3.Connection, smiles: str) -> CompoundRecord | None:
    """Return the first compound whose canonical SMILES matches, or None."""
    try:
        canonical = _canonical_smiles(smiles)
    except StructureInputError as e:
        raise DatabaseError(str(e)) from e
    row = conn.execute("SELECT * FROM compounds WHERE smiles = ?", (canonical,)).fetchone()
    if row is None:
        return None
    return _row_to_record(conn, row)


def all_compounds(conn: sqlite3.Connection) -> list[CompoundRecord]:
    """Return every compound in the database (the candidate set for structure search)."""
    rows = conn.execute("SELECT * FROM compounds ORDER BY compound_id").fetchall()
    return [_row_to_record(conn, row) for row in rows]


def delete_compound(conn: sqlite3.Connection, compound_id: str) -> bool:
    """Delete a compound (and its spectra). Returns True if a row was removed."""
    with conn:
        cursor = conn.execute(
            "DELETE FROM compounds WHERE compound_id = ?", (compound_id.strip(),)
        )
    return cursor.rowcount > 0


def make_record(
    *,
    compound_id: str,
    smiles: str,
    source_dir: str | None = None,
    created_at: str | None = None,
    spectra: dict[str, str] | None = None,
) -> CompoundRecord:
    """Build a :class:`CompoundRecord` from SMILES, computing canonical SMILES / formula / MW."""
    from chem_workflow.structure import mol_info

    try:
        mol = parse_smiles(smiles)
    except StructureInputError as e:
        raise DatabaseError(str(e)) from e
    info = mol_info(mol)
    return CompoundRecord(
        compound_id=compound_id.strip(),
        smiles=str(info["smiles"]),
        formula=str(info["formula"]),
        molecular_weight=float(info["mol_weight"]),
        source_dir=source_dir,
        created_at=created_at,
        spectra={k: v for k, v in (spectra or {}).items() if v and v.strip()},
    )


def make_literature_record(
    *,
    doi: str,
    smiles: str,
    title: str | None = None,
    authors: str | None = None,
    year: int | None = None,
    nmr_1h: str | None = None,
    nmr_13c: str | None = None,
    note: str | None = None,
) -> LiteratureRecord:
    """Build a :class:`LiteratureRecord`, canonicalizing the SMILES."""
    if not doi.strip():
        raise DatabaseError("doi 不能为空。")
    return LiteratureRecord(
        doi=doi.strip(),
        smiles=_canonical_smiles(smiles),
        title=_optional_str(title),
        authors=_optional_str(authors),
        year=year,
        nmr_1h=_optional_str(nmr_1h),
        nmr_13c=_optional_str(nmr_13c),
        note=_optional_str(note),
    )


def upsert_literature(conn: sqlite3.Connection, record: LiteratureRecord) -> None:
    """Insert or replace a literature reference keyed by DOI (idempotent)."""
    with conn:
        conn.execute(
            """
            INSERT INTO literature (doi, title, authors, year, smiles, nmr_1h, nmr_13c, note)
            VALUES (:doi, :title, :authors, :year, :smiles, :nmr_1h, :nmr_13c, :note)
            ON CONFLICT(doi) DO UPDATE SET
                title = excluded.title,
                authors = excluded.authors,
                year = excluded.year,
                smiles = excluded.smiles,
                nmr_1h = excluded.nmr_1h,
                nmr_13c = excluded.nmr_13c,
                note = excluded.note
            """,
            record.model_dump(),
        )


def all_literature(conn: sqlite3.Connection) -> list[LiteratureRecord]:
    """Return every literature reference (the candidate set for literature search)."""
    rows = conn.execute("SELECT * FROM literature ORDER BY doi").fetchall()
    return [_row_to_literature(row) for row in rows]


def get_literature_by_doi(conn: sqlite3.Connection, doi: str) -> LiteratureRecord | None:
    """Return the literature reference with this exact DOI, or None."""
    row = conn.execute("SELECT * FROM literature WHERE doi = ?", (doi.strip(),)).fetchone()
    return _row_to_literature(row) if row is not None else None


def delete_literature(conn: sqlite3.Connection, doi: str) -> bool:
    """Delete a literature reference. Returns True if a row was removed."""
    with conn:
        cursor = conn.execute("DELETE FROM literature WHERE doi = ?", (doi.strip(),))
    return cursor.rowcount > 0


def _row_to_literature(row: sqlite3.Row) -> LiteratureRecord:
    return LiteratureRecord(
        doi=row["doi"],
        smiles=row["smiles"],
        title=row["title"],
        authors=row["authors"],
        year=row["year"],
        nmr_1h=row["nmr_1h"],
        nmr_13c=row["nmr_13c"],
        note=row["note"],
    )

def record_from_metadata(metadata_path: str | Path) -> CompoundRecord:
    """Build a :class:`CompoundRecord` from a ``compounds/<id>/metadata.json`` file."""
    path = Path(metadata_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise DatabaseError(f"无法读取 metadata：{path}（{e}）") from e

    compound_id = str(data.get("compound_id") or "").strip()
    smiles = str(data.get("smiles") or "").strip()
    if not compound_id or not smiles:
        raise DatabaseError(f"metadata 缺少 compound_id 或 smiles：{path}")

    compound_dir = path.parent
    return CompoundRecord(
        compound_id=compound_id,
        smiles=smiles,
        formula=_optional_str(data.get("formula")),
        molecular_weight=_optional_float(data.get("molecular_weight")),
        source_dir=str(compound_dir),
        created_at=_optional_str(data.get("created_at")),
        spectra=_collect_spectra_texts(compound_dir),
    )


def scan_archive(project_dir: str | Path = Path(".")) -> list[CompoundRecord]:
    """Find all ``compounds/*/metadata.json`` under ``project_dir`` and build records."""
    root = Path(project_dir) / "compounds"
    if not root.exists():
        return []
    records: list[CompoundRecord] = []
    for metadata_path in sorted(root.glob("*/metadata.json")):
        records.append(record_from_metadata(metadata_path))
    return records


def _collect_spectra_texts(compound_dir: Path) -> dict[str, str]:
    """Best-effort read of any generated characterization text files in a compound folder."""
    spectra: dict[str, str] = {}
    candidates = {
        "1H": ("nmr/1H/formatted.txt", "nmr/1H/1H_nmr.txt"),
        "13C": ("nmr/13C/formatted.txt", "nmr/13C/13C_nmr.txt"),
        "HRMS": ("ms/hrms.txt", "ms/hrms_report.txt"),
        "IR": ("ir/ir.txt", "ir/ir_report.txt"),
        "UV": ("uv/uv.txt", "uv/uv_report.txt"),
    }
    for kind, rel_paths in candidates.items():
        for rel in rel_paths:
            file_path = compound_dir / rel
            if file_path.exists() and file_path.is_file():
                text = file_path.read_text(encoding="utf-8").strip()
                if text:
                    spectra[kind] = text
                    break
    return spectra


def _row_to_record(conn: sqlite3.Connection, row: sqlite3.Row) -> CompoundRecord:
    spectra_rows = conn.execute(
        "SELECT kind, text FROM spectra WHERE compound_pk = ? ORDER BY id", (row["id"],)
    ).fetchall()
    return CompoundRecord(
        compound_id=row["compound_id"],
        smiles=row["smiles"],
        formula=row["formula"],
        molecular_weight=row["molecular_weight"],
        source_dir=row["source_dir"],
        created_at=row["created_at"],
        spectra={s["kind"]: s["text"] for s in spectra_rows},
    )


def _canonical_smiles(smiles: str) -> str:
    from chem_workflow.structure import mol_info

    return str(mol_info(parse_smiles(smiles))["smiles"])


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


db_app = typer.Typer(help="本地历史数据库与检索命令", no_args_is_help=True)


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
    from chem_workflow.search import SearchError, similarity_search, substructure_search

    if substructure == similarity:
        typer.secho(
            "错误: 请二选一：--substructure 或 --similarity。", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)

    try:
        with closing(connect(db)) as conn:
            records = all_compounds(conn)
        if substructure:
            hits = substructure_search(records, smiles)
        else:
            hits = similarity_search(records, smiles, threshold=threshold, top_k=top_k)
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


lit_app = typer.Typer(help="本地文献参考与检索命令", no_args_is_help=True)


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
        title = record.title or "-"
        typer.echo(f"{record.doi:28s}  {record.year or '----'}  {title}  {record.smiles}")


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
    from chem_workflow.search import SearchError, similarity_search, substructure_search

    if substructure == similarity:
        typer.secho(
            "错误: 请二选一：--substructure 或 --similarity。", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)
    try:
        with closing(connect(db)) as conn:
            records = all_literature(conn)
        if substructure:
            hits = substructure_search(records, smiles)
        else:
            hits = similarity_search(records, smiles, threshold=threshold, top_k=top_k)
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
    from chem_workflow.search import SearchError, similarity_search

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
