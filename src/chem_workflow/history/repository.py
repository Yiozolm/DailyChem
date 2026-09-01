"""Phase 11 local history database (SQLite) for compounds and their spectra.

Stores compounds done in the lab so they can be searched later by ID / SMILES / substructure /
similarity (see :mod:`chem_workflow.search`). Fingerprints are not persisted; structure search
recomputes them on demand from the stored canonical SMILES, which keeps the schema simple and
robust across RDKit versions for the local scale this tool targets.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from chem_workflow.compounds.structure import StructureInputError, parse_smiles
from chem_workflow.history.models import CompoundRecord, DatabaseError, LiteratureRecord

DEFAULT_DB_PATH = Path("data/chem_workflow.sqlite")
SPECTRUM_KINDS = ("1H", "13C", "HRMS", "MS", "IR", "UV")


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
    from chem_workflow.compounds.structure import mol_info

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
    from chem_workflow.compounds.structure import mol_info

    return str(mol_info(parse_smiles(smiles))["smiles"])


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

