"""Phase 5 experiment record generation tests."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from chem_workflow.cli import app
from chem_workflow.records import (
    Characterization,
    Material,
    ReactionInfo,
    ReactionRecord,
    RecordInputError,
    load_reaction_record,
    render_experiment_record,
    write_experiment_record,
)

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "raw"
RECORD_FIXTURE = FIXTURES / "experiment_record_example.yaml"


def test_load_reaction_record_from_yaml() -> None:
    record = load_reaction_record(RECORD_FIXTURE)

    assert record.compound_id == "C001"
    assert record.product_name == "ethyl benzoate"
    assert record.reaction.starting_materials[0].name == "benzoic acid"
    assert record.yield_ is not None
    assert record.yield_.percent == "63%"
    assert record.characterization.h1_nmr is not None


def test_load_reaction_record_from_json(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    path.write_text(
        json.dumps(
            {
                "compound_id": "C002",
                "product_name": "anisole",
                "reaction": {
                    "starting_materials": [{"name": "phenol", "amount": "1 equiv"}],
                    "reagents": [{"name": "methyl iodide", "amount": "1.2 equiv"}],
                },
                "yield": {"mass": "88 mg"},
            }
        ),
        encoding="utf-8",
    )

    record = load_reaction_record(path)

    assert record.compound_id == "C002"
    assert record.yield_ is not None
    assert record.yield_.mass == "88 mg"


def test_render_english_record_contains_procedure_and_characterization() -> None:
    record = load_reaction_record(RECORD_FIXTURE)

    markdown = render_experiment_record(record, language="en")

    assert markdown.startswith("# Compound C001: ethyl benzoate")
    assert "To a solution of benzoic acid (1.0 mmol) and ethanol (5 mL) in ethanol" in markdown
    assert "The crude product was purified by column chromatography" in markdown
    assert "1H NMR (400 MHz, CDCl3)" in markdown
    assert "HRMS (ESI)" in markdown


def test_render_chinese_record_handles_missing_optional_fields() -> None:
    record = ReactionRecord(
        compound_id="C003",
        reaction=ReactionInfo(
            starting_materials=[Material(name="substrate")],
            temperature="room temperature",
        ),
        characterization=Characterization(h1_nmr="δ 7.26 (s, 1H)."),
    )

    markdown = render_experiment_record(record, language="zh")

    assert markdown.startswith("# 化合物 C003")
    assert "将substrate。" in markdown
    assert "反应液在room temperature下搅拌。" in markdown
    assert "1H NMR δ 7.26 (s, 1H)." in markdown


def test_render_record_without_characterization_does_not_crash() -> None:
    record = ReactionRecord(compound_id="C004")

    markdown = render_experiment_record(record)

    assert "Experimental procedure was not specified." in markdown
    assert "Not provided." in markdown


def test_write_experiment_record(tmp_path: Path) -> None:
    record = ReactionRecord(compound_id="C005", product_name="test compound")
    out = tmp_path / "nested" / "record.md"

    written = write_experiment_record(record, out)

    assert written == out
    assert out.read_text(encoding="utf-8").startswith("# Compound C005: test compound")


def test_load_reaction_record_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "record.txt"
    path.write_text("compound_id: C006", encoding="utf-8")

    with pytest.raises(RecordInputError, match="只支持"):
        load_reaction_record(path)


def test_cli_records_generate_outputs_markdown() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["records", "generate", str(RECORD_FIXTURE)])

    assert result.exit_code == 0
    assert "# Compound C001: ethyl benzoate" in result.output
    assert "13C NMR (101 MHz, CDCl3)" in result.output


def test_cli_records_generate_writes_markdown(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "experiment_record.md"

    result = runner.invoke(
        app,
        ["records", "generate", str(RECORD_FIXTURE), "--language", "zh", "--out", str(out)],
    )

    assert result.exit_code == 0
    assert result.output == f"已写入 {out}\n"
    assert out.read_text(encoding="utf-8").startswith("# 化合物 C001：ethyl benzoate")
