"""Local compound and literature history storage and search."""

from chem_workflow.history.importers import record_from_metadata, scan_archive
from chem_workflow.history.models import CompoundRecord, DatabaseError, LiteratureRecord
from chem_workflow.history.repository import (
    DEFAULT_DB_PATH,
    SPECTRUM_KINDS,
    all_compounds,
    all_literature,
    connect,
    delete_compound,
    delete_literature,
    find_by_smiles,
    get_compound,
    get_literature_by_doi,
    make_literature_record,
    make_record,
    upsert_compound,
    upsert_literature,
)

__all__ = [
    "DEFAULT_DB_PATH",
    "SPECTRUM_KINDS",
    "CompoundRecord",
    "DatabaseError",
    "LiteratureRecord",
    "all_compounds",
    "all_literature",
    "connect",
    "delete_compound",
    "delete_literature",
    "find_by_smiles",
    "get_compound",
    "get_literature_by_doi",
    "make_literature_record",
    "make_record",
    "record_from_metadata",
    "scan_archive",
    "upsert_compound",
    "upsert_literature",
]
