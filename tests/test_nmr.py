"""Phase 3 NMR multiplet 表解析测试。"""

import json
from pathlib import Path

import pytest

from chem_workflow.nmr import (
    NMRInputError,
    NMRPeak,
    NMRSpectrum,
    normalize_multiplicity,
    parse_j_values,
    parse_mestrenova_multiplet_table,
    parse_shift_range,
)

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "raw"
MULTIPLET_FIXTURE = FIXTURES / "nmr_multiplet_table_example.tsv"
MULTIPLET_NEWLINE_FIXTURE = FIXTURES / "nmr_multiplet_table_newline_example.tsv"
MULTIPLET_CLEAN_FIXTURE = FIXTURES / "nmr_multiplet_table_clean_example.tsv"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("singlet", "s"),
        ("doublet", "d"),
        ("Triplet", "t"),
        ("doublet of doublets", "dd"),
        ("doublet of doublet of doublets", "ddd"),
        ("multiplet", "m"),
        ("  Quartet  ", "q"),
        ("broad singlet", "br s"),
    ],
)
def test_normalize_multiplicity_aliases(raw, expected):
    assert normalize_multiplicity(raw) == expected


def test_normalize_multiplicity_already_canonical():
    assert normalize_multiplicity("dd") == "dd"
    assert normalize_multiplicity("s") == "s"


def test_normalize_multiplicity_empty_and_none():
    assert normalize_multiplicity("") == ""
    assert normalize_multiplicity("   ") == ""
    assert normalize_multiplicity(None) == ""


def test_normalize_multiplicity_unknown_passes_through():
    # 没在 alias 表里，按 lower+strip 保留原值（parser 端会 warn）
    assert normalize_multiplicity("zzz") == "zzz"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("97.06", [97.06]),
        ("8.0, 2.0", [8.0, 2.0]),
        ("J = 8.0 Hz", [8.0]),
        ("J1 = 8.0, J2 = 2.0 Hz", [8.0, 2.0]),
        ("8.0;2.0", [8.0, 2.0]),
        ("", []),
        (None, []),
        ("   ", []),
    ],
)
def test_parse_j_values(raw, expected):
    assert parse_j_values(raw) == expected


def test_parse_shift_range_dotdot():
    assert parse_shift_range("8.86 .. 8.29") == (8.29, 8.86)


def test_parse_shift_range_endash():
    assert parse_shift_range("7.80–7.23") == (7.23, 7.80)


def test_parse_shift_range_empty_and_none():
    assert parse_shift_range("") is None
    assert parse_shift_range(None) is None
    assert parse_shift_range("   ") is None


def test_parse_shift_range_single_number_returns_none():
    # 不够 2 个数字时返回 None（不构成区间）
    assert parse_shift_range("8.56") is None


def test_parse_multiplet_table_fixture():
    """用同学给的 multiplet 表 fixture 端到端解析。

    数据本身的化学值是脏的（杂质峰被合并），但格式契约是稳定的，
    parser 应忠实解析。"""
    spectrum = parse_mestrenova_multiplet_table(
        MULTIPLET_FIXTURE,
        frequency_mhz=400,
        solvent="CDCl3",
    )
    assert spectrum.nucleus == "1H"
    assert spectrum.frequency_mhz == 400
    assert spectrum.solvent == "CDCl3"
    assert len(spectrum.peaks) == 6

    f_peak = spectrum.peaks[0]
    assert f_peak.shift_ppm == pytest.approx(8.56)
    assert f_peak.shift_range == (8.29, 8.86)
    assert f_peak.integration == pytest.approx(1.0)
    assert f_peak.multiplicity == "s"
    assert f_peak.j_hz == []
    assert f_peak.assignment == "F"

    d_peak = spectrum.peaks[2]
    assert d_peak.shift_ppm == pytest.approx(3.23)
    assert d_peak.multiplicity == "d"
    assert d_peak.j_hz == [pytest.approx(97.06)]
    assert d_peak.integration == pytest.approx(45.0)
    assert d_peak.assignment == "D"


def test_parse_multiplet_table_clean_fixture():
    """同学修完基准后的第三份样例：H's 列与 Integral 自洽，总氢数 19H。

    这是 Phase 4 formatter 后续端到端测试的参考输入。"""
    spectrum = parse_mestrenova_multiplet_table(
        MULTIPLET_CLEAN_FIXTURE,
        frequency_mhz=400,
        solvent="CDCl3",
    )
    assert len(spectrum.peaks) == 6
    assert sum(p.integration or 0 for p in spectrum.peaks) == pytest.approx(19.0)

    # A 是基准 9H 峰，δ 3.11
    a_peak = next(p for p in spectrum.peaks if p.assignment == "A")
    assert a_peak.shift_ppm == pytest.approx(3.11)
    assert a_peak.integration == pytest.approx(9.0)

    # 其他 5 个峰各 2H、都是单峰
    others = [p for p in spectrum.peaks if p.assignment != "A"]
    assert all(p.integration == pytest.approx(2.0) for p in others)
    assert all(p.multiplicity == "s" for p in others)


def test_parse_multiplet_table_newline_layout_fixture():
    """同学第二份样例：每字段独占一行 + 空行分隔每组（tab 被换行替换的复制粘贴姿态）。

    数据本身是化学侧基准设反（A=9H 而非 1H 导致其他峰 round 到 0），
    parser 仍应忠实解析，不在 Phase 3 做 sanity check。"""
    spectrum = parse_mestrenova_multiplet_table(
        MULTIPLET_NEWLINE_FIXTURE,
        frequency_mhz=400,
        solvent="CDCl3",
    )
    assert len(spectrum.peaks) == 6

    f_peak = spectrum.peaks[0]
    assert f_peak.shift_ppm == pytest.approx(8.56)
    assert f_peak.shift_range == (8.34, 8.72)
    assert f_peak.integration == pytest.approx(0.0)  # 被基准错误 round 到 0
    assert f_peak.multiplicity == "s"
    assert f_peak.assignment == "F"

    a_peak = spectrum.peaks[5]
    assert a_peak.shift_ppm == pytest.approx(3.11)
    assert a_peak.integration == pytest.approx(9.0)  # 同学设为 9H 的那个基准峰
    assert a_peak.assignment == "A"


def test_parse_multiplet_table_newline_layout_inline():
    """直接贴 newline-separated 文本块。"""
    text = (
        "Name\nShift\nClass\nJ's\n"
        "\n"
        "A (d)\n7.26\nd\n8.0\n"
        "\n"
        "B (s)\n3.85\ns\n\n"  # B 没有 J 值
    )
    spectrum = parse_mestrenova_multiplet_table(text)
    assert len(spectrum.peaks) == 2
    assert spectrum.peaks[0].j_hz == [8.0]
    assert spectrum.peaks[1].j_hz == []


def test_parse_multiplet_table_newline_layout_preserves_tab_path():
    """newline-normalize 不应该破坏原 tab-separated 输入。"""
    text = "Name\tShift\tClass\nA\t7.26\ts\n"
    spectrum = parse_mestrenova_multiplet_table(text)
    assert spectrum.peaks[0].shift_ppm == pytest.approx(7.26)


def test_parse_multiplet_table_inline_text():
    """直接接受贴入的文本块（不一定是文件）。"""
    text = (
        "Name\tShift\tRange\tH's\tIntegral\tClass\tJ's\n"
        "1\tA (s)\t7.26\t7.30 .. 7.20\t1\t1.00\ts\n"
        "2\tB (d)\t3.85\t3.90 .. 3.80\t3\t3.05\td\t8.0\n"
    )
    spectrum = parse_mestrenova_multiplet_table(text)
    assert len(spectrum.peaks) == 2
    assert spectrum.peaks[1].j_hz == [8.0]
    """直接接受贴入的文本块（不一定是文件）。"""
    text = (
        "Name\tShift\tRange\tH's\tIntegral\tClass\tJ's\n"
        "1\tA (s)\t7.26\t7.30 .. 7.20\t1\t1.00\ts\n"
        "2\tB (d)\t3.85\t3.90 .. 3.80\t3\t3.05\td\t8.0\n"
    )
    spectrum = parse_mestrenova_multiplet_table(text)
    assert len(spectrum.peaks) == 2
    assert spectrum.peaks[1].j_hz == [8.0]


def test_parse_multiplet_table_short_row_pads():
    """单峰行末尾 J's 列为空被吞掉时，parser 应 pad 成空串而不是 raise。"""
    text = (
        "Name\tShift\tClass\tJ's\n"
        # 第二行只有 3 列（J's 被 trailing-tab 吞了）
        "A (s)\t7.26\ts\n"
    )
    spectrum = parse_mestrenova_multiplet_table(text)
    assert len(spectrum.peaks) == 1
    assert spectrum.peaks[0].j_hz == []


def test_parse_multiplet_table_missing_shift_column():
    text = "Name\tClass\nA\ts\n"
    with pytest.raises(NMRInputError, match="找不到 multiplet 表头"):
        parse_mestrenova_multiplet_table(text)


def test_parse_multiplet_table_invalid_shift_value():
    text = "Name\tShift\tClass\nA\tNotANumber\ts\n"
    with pytest.raises(NMRInputError, match="Shift 非数值"):
        parse_mestrenova_multiplet_table(text)


def test_parse_multiplet_table_empty_data_rows():
    text = "Name\tShift\tClass\n"
    with pytest.raises(NMRInputError, match="multiplet 表为空"):
        parse_mestrenova_multiplet_table(text)


def test_parse_multiplet_table_unknown_multiplicity_warns():
    text = (
        "Name\tShift\tClass\n"
        "A\t7.26\txyzzz\n"
    )
    with pytest.warns(UserWarning, match="未识别的 multiplicity"):
        spectrum = parse_mestrenova_multiplet_table(text)
    # 未识别的值按 lowercase 保留，不丢弃
    assert spectrum.peaks[0].multiplicity == "xyzzz"


def test_parse_multiplet_table_space_separated_rejected():
    """空格分隔（而非 tab）应被拒，避免错把表头当数据。"""
    text = "Shift Class\n7.26 s\n"
    with pytest.raises(NMRInputError, match="Tab"):
        parse_mestrenova_multiplet_table(text)


def test_parse_multiplet_table_case_insensitive_columns():
    """列名大小写不敏感（H'S vs H's, SHIFT vs Shift）。"""
    text = (
        "NAME\tSHIFT\tCLASS\tJ'S\n"
        "A (d)\t7.26\td\t8.0\n"
    )
    spectrum = parse_mestrenova_multiplet_table(text)
    assert spectrum.peaks[0].shift_ppm == pytest.approx(7.26)
    assert spectrum.peaks[0].multiplicity == "d"
    assert spectrum.peaks[0].j_hz == [8.0]


def test_spectrum_json_roundtrip():
    """`.model_dump_json()` 是合法 JSON 且能反序列化回来。"""
    spectrum = parse_mestrenova_multiplet_table(
        MULTIPLET_FIXTURE, frequency_mhz=400, solvent="CDCl3"
    )
    payload = spectrum.model_dump_json()
    data = json.loads(payload)  # 合法 JSON
    assert data["nucleus"] == "1H"
    assert len(data["peaks"]) == 6
    # 反序列化
    restored = NMRSpectrum.model_validate_json(payload)
    assert restored == spectrum


def test_peak_model_defaults():
    """最小构造：只有 shift_ppm 必填。"""
    peak = NMRPeak(shift_ppm=7.26)
    assert peak.shift_range is None
    assert peak.integration is None
    assert peak.multiplicity is None
    assert peak.j_hz == []
    assert peak.assignment is None
