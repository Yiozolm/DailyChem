"""Phase 11 local history database tests."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from chem_workflow.cli import app
from chem_workflow.database import (
    DatabaseError,
    all_compounds,
    connect,
    delete_compound,
    find_by_smiles,
    get_compound,
    make_record,
    record_from_metadata,
    scan_archive,
    upsert_compound,
)
from chem_workflow.storage import init_compound_archive

ETHYL_BENZOATE = "CCOC(=O)c1ccccc1"
METHYL_BENZOATE = "COC(=O)c1ccccc1"


def _db(tmp_path: Path):
    return connect(tmp_path / "history.sqlite")


def test_connect_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite"
    with closing(connect(path)):
        pass
    with closing(connect(path)) as conn:  # second open must not fail
        assert all_compounds(conn) == []


def test_upsert_and_get_with_spectra(tmp_path: Path) -> None:
    with closing(_db(tmp_path)) as conn:
        record = make_record(
            compound_id="C001",
            smiles=ETHYL_BENZOATE,
            spectra={"HRMS": "HRMS (ESI) ...", "1H": "1H NMR ..."},
        )
        upsert_compound(conn, record)

        fetched = get_compound(conn, "C001")
        assert fetched is not None
        assert fetched.formula == "C9H10O2"
        assert fetched.spectra["HRMS"] == "HRMS (ESI) ..."
        assert fetched.spectra["1H"] == "1H NMR ..."


def test_upsert_is_idempotent(tmp_path: Path) -> None:
    with closing(_db(tmp_path)) as conn:
        record = make_record(compound_id="C001", smiles=ETHYL_BENZOATE)
        upsert_compound(conn, record)
        upsert_compound(conn, record)  # second time updates, does not duplicate

        assert len(all_compounds(conn)) == 1


def test_upsert_replaces_spectra(tmp_path: Path) -> None:
    with closing(_db(tmp_path)) as conn:
        upsert_compound(
            conn, make_record(compound_id="C001", smiles=ETHYL_BENZOATE, spectra={"HRMS": "old"})
        )
        upsert_compound(
            conn, make_record(compound_id="C001", smiles=ETHYL_BENZOATE, spectra={"1H": "new"})
        )
        fetched = get_compound(conn, "C001")
        assert fetched is not None
        assert fetched.spectra == {"1H": "new"}


def test_find_by_smiles_canonicalizes(tmp_path: Path) -> None:
    with closing(_db(tmp_path)) as conn:
        upsert_compound(conn, make_record(compound_id="C001", smiles=ETHYL_BENZOATE))
        # A differently written but equivalent SMILES must still match.
        found = find_by_smiles(conn, "O=C(OCC)c1ccccc1")
        assert found is not None
        assert found.compound_id == "C001"


def test_delete_compound(tmp_path: Path) -> None:
    with closing(_db(tmp_path)) as conn:
        upsert_compound(conn, make_record(compound_id="C001", smiles=ETHYL_BENZOATE))
        assert delete_compound(conn, "C001") is True
        assert delete_compound(conn, "C001") is False
        assert get_compound(conn, "C001") is None


def test_make_record_rejects_invalid_smiles() -> None:
    with pytest.raises(DatabaseError):
        make_record(compound_id="C001", smiles="not-a-smiles")


def test_scan_archive_reads_metadata(tmp_path: Path) -> None:
    init_compound_archive(compound_id="C001", project_dir=tmp_path, smiles=ETHYL_BENZOATE)
    records = scan_archive(tmp_path)

    assert len(records) == 1
    assert records[0].compound_id == "C001"
    assert records[0].formula == "C9H10O2"
    assert records[0].source_dir is not None


def test_scan_archive_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert scan_archive(tmp_path / "nope") == []


def test_record_from_metadata_requires_fields(tmp_path: Path) -> None:
    bad = tmp_path / "metadata.json"
    bad.write_text('{"compound_id": "", "smiles": ""}', encoding="utf-8")
    with pytest.raises(DatabaseError, match="缺少"):
        record_from_metadata(bad)


def test_cli_db_add_and_search_substructure(tmp_path: Path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "history.sqlite")

    add1 = runner.invoke(app, ["db", "add", "--id", "C001", "-s", ETHYL_BENZOATE, "--db", db])
    add2 = runner.invoke(app, ["db", "add", "--id", "C002", "-s", METHYL_BENZOATE, "--db", db])
    assert add1.exit_code == 0
    assert add2.exit_code == 0

    result = runner.invoke(app, ["db", "search", "-s", "c1ccccc1", "--substructure", "--db", db])

    assert result.exit_code == 0
    assert "C001" in result.output
    assert "C002" in result.output


def test_cli_db_search_similarity_orders_by_score(tmp_path: Path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "history.sqlite")
    runner.invoke(app, ["db", "add", "--id", "C001", "-s", ETHYL_BENZOATE, "--db", db])
    runner.invoke(app, ["db", "add", "--id", "C002", "-s", METHYL_BENZOATE, "--db", db])

    result = runner.invoke(
        app,
        ["db", "search", "-s", ETHYL_BENZOATE, "--similarity", "--threshold", "0.4", "--db", db],
    )

    assert result.exit_code == 0
    # C001 (exact) ranks before C002.
    assert result.output.index("C001") < result.output.index("C002")


def test_cli_db_search_requires_one_mode(tmp_path: Path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "history.sqlite")

    result = runner.invoke(app, ["db", "search", "-s", "c1ccccc1", "--db", db])

    assert result.exit_code == 1
    assert "二选一" in result.output


def test_cli_db_import_from_archive(tmp_path: Path) -> None:
    init_compound_archive(compound_id="C001", project_dir=tmp_path, smiles=ETHYL_BENZOATE)
    runner = CliRunner()
    db = str(tmp_path / "history.sqlite")

    result = runner.invoke(app, ["db", "import", "-p", str(tmp_path), "--db", db])

    assert result.exit_code == 0
    assert "已导入 1 个化合物" in result.output


def test_literature_upsert_and_get(tmp_path: Path) -> None:
    from chem_workflow.database import (
        get_literature_by_doi,
        make_literature_record,
        upsert_literature,
    )

    with closing(_db(tmp_path)) as conn:
        record = make_literature_record(
            doi="10.1/x",
            smiles="O=C(OCC)c1ccccc1",  # non-canonical input
            title="Ester paper",
            nmr_13c="13C NMR δ 166.7, 60.9, 14.4.",
        )
        upsert_literature(conn, record)

        fetched = get_literature_by_doi(conn, "10.1/x")
        assert fetched is not None
        assert fetched.smiles == "CCOC(=O)c1ccccc1"  # canonicalized
        assert fetched.title == "Ester paper"
        assert fetched.nmr_13c.startswith("13C NMR")


def test_literature_upsert_idempotent(tmp_path: Path) -> None:
    from chem_workflow.database import (
        all_literature,
        make_literature_record,
        upsert_literature,
    )

    with closing(_db(tmp_path)) as conn:
        rec = make_literature_record(doi="10.1/x", smiles=ETHYL_BENZOATE)
        upsert_literature(conn, rec)
        upsert_literature(conn, rec)
        assert len(all_literature(conn)) == 1


def test_cli_lit_add_and_search(tmp_path: Path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "history.sqlite")
    runner.invoke(app, ["lit", "add", "--doi", "10.1/x", "-s", ETHYL_BENZOATE, "--db", db])
    runner.invoke(app, ["lit", "add", "--doi", "10.1/y", "-s", METHYL_BENZOATE, "--db", db])

    result = runner.invoke(app, ["lit", "search", "-s", "c1ccccc1", "--substructure", "--db", db])

    assert result.exit_code == 0
    assert "10.1/x" in result.output
    assert "10.1/y" in result.output


def test_cli_lit_compare(tmp_path: Path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "history.sqlite")
    runner.invoke(
        app,
        [
            "lit", "add", "--doi", "10.1/x", "-s", ETHYL_BENZOATE,
            "--c13", "13C δ 166.7.", "--db", db,
        ],
    )

    result = runner.invoke(app, ["lit", "compare", "-s", ETHYL_BENZOATE, "--db", db])

    assert result.exit_code == 0
    assert "10.1/x" in result.output
    assert "13C δ 166.7." in result.output
