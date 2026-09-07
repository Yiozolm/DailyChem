"""Phase 0/12 golden-output regression tests.

Each test asserts that current module output exactly matches a checked-in golden file under
``examples/expected_outputs/``. If output formatting changes intentionally, regenerate the golden
files (see ``examples/expected_outputs/README.md``) and commit them alongside the code change.
"""

from __future__ import annotations

from pathlib import Path

from chem_workflow.ir import format_ir, parse_ir_peaks
from chem_workflow.ms import compute_hrms, format_hrms
from chem_workflow.nmr import parse_mestrenova_multiplet_table
from chem_workflow.nmr_formatter import NMRFormatOptions, format_nmr_spectrum
from chem_workflow.records import load_reaction_record, render_experiment_record
from chem_workflow.uv import format_uv, parse_uv_peaks

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "examples" / "raw"
EXPECTED = ROOT / "examples" / "expected_outputs"


def _golden(name: str) -> str:
    return (EXPECTED / name).read_text(encoding="utf-8")


def test_nmr_1h_report_matches_golden() -> None:
    tsv = (RAW / "nmr_multiplet_table_clean_example.tsv").read_text(encoding="utf-8")
    spectrum = parse_mestrenova_multiplet_table(
        tsv, nucleus="1H", frequency_mhz=400, solvent="CDCl3"
    )
    output = format_nmr_spectrum(spectrum, NMRFormatOptions()) + "\n"

    assert output == _golden("nmr_report_1H.txt")


def test_hrms_report_matches_golden() -> None:
    result = compute_hrms(smiles="CCOC(=O)c1ccccc1", adduct="[M+Na]+", found_mz=173.0570)
    output = format_hrms(result) + "\n"

    assert output == _golden("hrms_report.txt")


def test_ir_report_matches_golden() -> None:
    spectrum = parse_ir_peaks((RAW / "ir_peaks_example.txt").read_text(encoding="utf-8"))
    output = format_ir(spectrum) + "\n"

    assert output == _golden("ir_report.txt")


def test_uv_report_matches_golden() -> None:
    spectrum = parse_uv_peaks(
        (RAW / "uv_peaks_example.txt").read_text(encoding="utf-8"), solvent="MeOH"
    )
    output = format_uv(spectrum) + "\n"

    assert output == _golden("uv_report.txt")


def test_experiment_record_en_matches_golden() -> None:
    record = load_reaction_record(RAW / "experiment_record_example.yaml")
    output = render_experiment_record(record, "en") + "\n"

    assert output == _golden("experiment_record_en.md")


def test_experiment_record_zh_matches_golden() -> None:
    record = load_reaction_record(RAW / "experiment_record_example.yaml")
    output = render_experiment_record(record, "zh") + "\n"

    assert output == _golden("experiment_record_zh.md")
