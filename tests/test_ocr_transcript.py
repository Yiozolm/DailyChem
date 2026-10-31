"""Tests for transcript-based OCR drafts and stoichiometry checks.

Fixtures are trimmed GLM-OCR ``Text Recognition:`` outputs for ``examples/raw/note/*.jpg``.
"""

from __future__ import annotations

import pytest

from chem_workflow.ocr import (
    OCRClientError,
    OCRImage,
    OCRService,
    OCRServiceError,
    OCRTableRow,
    check_material_table,
    check_yield,
    clean_transcript,
    draft_from_transcript,
    parse_material_table,
)
from chem_workflow.ocr.stoichiometry import parse_quantity

NOTE_1 = """1) MeI. $K_2CO_3$ $\\rightarrow$ DMF
2) 2M NaOH, MEOH, 60°C

Compound. M ef n m V d
I 332.3 1.0 1.50mmol 0.5g
$K_2CO_3$ 138.21 2.0 3.00mmol 0.415g
MeI 141.94 2.0 3.00mmol 0.428g 187mL 2.28.
DMF 1.5mL

- 15:36 To the mixture of I, $K_2CO_3$ and DMF, add MeI (1.2ef, 112mL) dropwise
- 19:13 The compound I spot on TLC remain concentrated. Add MeI (0.8ef, 75mL).
- 22:47 Color of reaction mixture changed from dark red to light orange.
Quench the reaction with water, extract with EtOAc 3 times, wash with brine, dry under vac.

Column: 30% EtOAc in Hexane.
Yield: 21.6%

Continued on Page

12/16/2024

Signed Date Signed Date
"""

NOTE_2 = """I
346.3 1.0 144.3 mmol 50mg
II 102.56 1.5 216.45 mmol 22.22mg 24.34 mL 0.913
CuCl₂ 134.45 0.01 1.44 mmol 0.19mg
DBU 152.24 1.1 158.73 mmol 24.17mg 23.71 mL 1.02
meCN 0.5mL

- 16:00 Add DBU to the solution of I. CuCl₂. MeCN (Solution turned from orange to black instantly) Then add II.
- 12:56 (11/0) TLC showed incomplete conversion. Evaporate the solvent on rot to vape. Load the mixture on normal phase column. (1% MeOH in DCM).
- Yield: 10 mg (16%)
"""  # noqa: E501

NOTE_4 = """I
Compound M eb n m v d
I 122.12 1.0 0.41 mmol 50 mg 43 mL 1.16
II 30.03 1.64 0.672 mmol 20mg 13 mL 3.8 mL (37%)
HCl
H₂SO₄
1 drop

- 20:00 Add I. II. HCl. and 1 drop of H₂SO₄ in a tube. Heat to 70°C.
Re-crystallize with EtOH, to obtain 67mg white needle-like solid.
Yield: 97%
"""

NOTE_5 = """$$\\text{Et}_2\\text{NOH} \\xrightarrow{2\\% \\text{Et}_2\\text{LNCH}_3, 50^\\circ\\text{C}, 3\\text{h}} \\text{Et}_2\\text{NOH}$$

| Compound | M | ef | n | m | v | d |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| I | 491.3 | 1.0 | 12.2 $\\mu$mol | 6 mg | | |
| Et$_2$NOH | 89.14 | 4.0 | 48.8 $\\mu$mol | 4.35 mg | 4.92 mL | 0.885 mL |

- 15:00 Dissolve I in co-solvent, Add Et$_2$NOH and heat to 50°C
- 13:05(211) Remove solvent on notvape in ice bath
Run the column with 15-20% CMA.
Yield 10mg (142%) May because of the solvent not removed completely.
NMR not clear. The product decomposed a little bit.
"""  # noqa: E501


def _unit_warnings(warnings: list[str]) -> list[str]:
    return [warning for warning in warnings if "相差 1000 倍" in warning]


def test_clean_transcript_strips_latex_and_normalizes_units() -> None:
    cleaned = clean_transcript("Et$_2$NOH 12.2 $\\mu$mol 4.35 µL 40℃ CuCl₂ 50^\\circ\\text{C}")

    assert cleaned == "Et2NOH 12.2 μmol 4.35 μL 40°C CuCl2 50°C"


def test_whitespace_table_maps_amounts_roles_and_sections() -> None:
    draft = draft_from_transcript(NOTE_1)

    assert [row.name for row in draft.material_table] == ["I", "K2CO3", "MeI", "DMF"]
    assert [item.as_form_line() for item in draft.starting_materials] == [
        "I | 0.5 g, 1.50 mmol, 1.0 equiv"
    ]
    assert [item.as_form_line() for item in draft.reagents] == [
        "K2CO3 | 0.415 g, 3.00 mmol, 2.0 equiv",
        "MeI | 0.428 g, 187 mL, 3.00 mmol, 2.0 equiv",
    ]
    assert draft.solvent.value == "DMF (1.5 mL)"
    assert draft.procedure.value.startswith("15:36 To the mixture of I")
    assert "remain concentrated" in draft.procedure.value
    assert draft.workup.value.startswith("Quench the reaction with water")
    assert draft.purification.value == "Column: 30% EtOAc in Hexane."
    assert draft.yield_percent.value == "21.6%"
    assert "Signed" not in (draft.procedure.value or "")
    # MeI: 0.428 g / 2.28 g/mL = 187.7 µL, so "187 mL" is a µ/m misread.
    assert [w.split("：")[0] for w in _unit_warnings(draft.warnings)] == ["MeI"]


def test_headerless_table_joins_label_line_and_flags_mmol_for_umol() -> None:
    draft = draft_from_transcript(NOTE_2)

    first = draft.material_table[0]
    assert (first.name, first.molar_mass, first.amount, first.mass) == (
        "I",
        "346.3",
        "144.3 mmol",
        "50 mg",
    )
    assert draft.solvent.value == "meCN (0.5 mL)"
    assert [item.name.value for item in draft.reagents] == ["CuCl2", "DBU"]
    flagged = [w.split("：")[0] for w in _unit_warnings(draft.warnings)]
    assert flagged == ["I", "II", "II", "CuCl2", "DBU", "DBU"]
    assert draft.workup.value == "Evaporate the solvent on rot to vape."
    assert draft.purification.value.startswith("Load the mixture on normal phase column")
    assert "TLC showed incomplete conversion." in draft.procedure.value
    assert (draft.yield_mass.value, draft.yield_percent.value) == ("10 mg", "16%")


def test_drop_rows_extra_values_appearance_and_obtained_mass() -> None:
    draft = draft_from_transcript(NOTE_4)

    rows = {row.name: row for row in draft.material_table}
    assert rows["H2SO4"].volume == "1 drop"
    assert rows["HCl"].volume is None
    assert rows["II"].note == "3.8 mL (37%)"
    assert any("II 行有多余数值" in warning for warning in draft.warnings)
    assert draft.temperature.value == "70 °C"
    assert draft.appearance.value == "white needle-like solid"
    assert draft.yield_mass.value == "67 mg"
    assert draft.purification.value.startswith("Re-crystallize with EtOH")


def test_markdown_table_with_latex_units_and_yield_over_100() -> None:
    draft = draft_from_transcript(NOTE_5)

    rows = {row.name: row for row in draft.material_table}
    assert rows["I"].amount == "12.2 μmol"
    assert rows["Et2NOH"].density == "0.885"
    assert any("d列" in warning for warning in draft.warnings)
    assert [w.split("：")[0] for w in _unit_warnings(draft.warnings)] == ["Et2NOH"]
    assert any("超过 100%" in warning for warning in draft.warnings)
    assert draft.time.value == "3 h"
    assert draft.temperature.value == "50 °C"
    assert draft.workup.value.startswith("13:05(211) Remove solvent")
    assert draft.purification.value == "Run the column with 15-20% CMA."
    assert "NMR not clear." in draft.unmapped_text


def test_parse_material_table_returns_empty_without_table() -> None:
    rows, warnings = parse_material_table("Add MeI dropwise.\nQuench with water.")

    assert rows == []
    assert warnings == []
    draft = draft_from_transcript("Add MeI dropwise.")
    assert any("未识别到试剂表" in warning for warning in draft.warnings)


@pytest.mark.parametrize(
    ("text", "unit", "base"),
    [("24.34 uL", "μL", 0.02434), ("1.5ML", "mL", 1.5), ("12.1µmol", "μmol", 12.1e-6)],
)
def test_parse_quantity_accepts_ocr_unit_spellings(text: str, unit: str, base: float) -> None:
    quantity = parse_quantity(text)

    assert quantity is not None
    assert quantity.unit == unit
    assert quantity.base == pytest.approx(base)


def test_consistent_table_has_no_warnings_but_wrong_equivalents_do() -> None:
    rows = [
        OCRTableRow(
            name="I", molar_mass="412.44", equivalents="1.0", amount="121.2 μmol", mass="50 mg"
        ),
        OCRTableRow(
            name="NBS", molar_mass="177.98", equivalents="1.1", amount="133.4 μmol", mass="23.73 mg"
        ),
    ]
    assert check_material_table(rows) == []

    rows[1] = rows[1].model_copy(update={"equivalents": "2.0"})
    messages = check_material_table(rows)
    assert len(messages) == 1
    assert messages[0].startswith("NBS：当量写作 2.0")


def test_check_yield_with_product_molar_mass() -> None:
    rows = [
        OCRTableRow(name="I", molar_mass="412.44", equivalents="1.0", mass="50 mg"),
    ]
    # 10 mg of a 491.3 g/mol product from 121.2 µmol is 16.8%, not 6%.
    mismatch = check_yield(rows, "10 mg", "6%", product_mw=491.3)
    assert len(mismatch) == 1
    assert "16.8%" in mismatch[0]

    assert check_yield(rows, "10 mg", "16%", product_mw=491.3) == []


class _FakeClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[list[str], str]] = []

    def recognize(self, images, prompt):  # noqa: ANN001
        self.calls.append(([image.name for image in images], prompt))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def extract_content(self, response):  # noqa: ANN001
        return response["choices"][0]["message"]["content"]


def _response(content: str, finish_reason: str = "stop") -> dict[str, object]:
    return {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}


def test_service_sends_one_native_prompt_per_page_and_keeps_good_pages() -> None:
    client = _FakeClient(
        [
            _response(NOTE_1),
            OCRClientError("timeout"),
            _response("Yield: 21.6%", finish_reason="length"),
        ]
    )
    images = [OCRImage("1.jpg", b"a"), OCRImage("2.jpg", b"b"), OCRImage("3.jpg", b"c")]

    draft, raw_response, content = OCRService(client).recognize(images)

    assert client.calls == [
        (["1.jpg"], "Text Recognition:"),
        (["2.jpg"], "Text Recognition:"),
        (["3.jpg"], "Text Recognition:"),
    ]
    assert draft.page_count == 3
    assert draft.material_table
    assert any("第 2 张照片（2.jpg）识别失败" in warning for warning in draft.warnings)
    assert any("第 3 张照片的识别输出达到长度上限" in warning for warning in draft.warnings)
    assert [page["image"] for page in raw_response["pages"]] == ["1.jpg", "2.jpg", "3.jpg"]
    assert content.endswith("Yield: 21.6%")


def test_service_raises_when_every_page_fails() -> None:
    client = _FakeClient([OCRClientError("down")])

    with pytest.raises(OCRServiceError, match="所有照片都识别失败"):
        OCRService(client).recognize([OCRImage("1.jpg", b"a")])
