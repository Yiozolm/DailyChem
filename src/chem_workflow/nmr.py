"""NMR peak list 数据模型与解析。

第一版只接 MestReNova multiplet 表（`View → Tables → Multiplets` 直接复制粘贴的
tab-separated 文本）。决策见 `docs/design-docs/nmr-input-strategy.md`。
"""

import re
import warnings
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class NMRInputError(ValueError):
    """NMR 输入解析失败时抛出。错误信息会展示给用户，应包含可操作建议。"""


_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_J_PREFIX_RE = re.compile(r"\bJ\d*\s*=\s*", flags=re.IGNORECASE)
_HZ_SUFFIX_RE = re.compile(r"\bHz\b", flags=re.IGNORECASE)

_MULT_ALIASES = {
    "singlet": "s",
    "doublet": "d",
    "triplet": "t",
    "quartet": "q",
    "pentet": "p",
    "quintet": "quint",
    "sextet": "sext",
    "septet": "sept",
    "multiplet": "m",
    "broad": "br",
    "broad singlet": "br s",
    "doublet of doublets": "dd",
    "doublet of triplets": "dt",
    "triplet of doublets": "td",
    "doublet of quartets": "dq",
    "quartet of doublets": "qd",
    "doublet of doublet of doublets": "ddd",
}

KNOWN_MULTIPLICITIES = frozenset(
    {
        "s", "d", "t", "q", "p", "quint", "sext", "sept", "m",
        "dd", "dt", "td", "tt", "dq", "qd", "ddd", "dddd",
        "br", "br s", "br d", "br t", "br m",
    }
)

# 列名别名（大小写不敏感比较）；MestReNova 的标头是 "Name / Shift / Range / H's /
# Integral / Class / J's"，但其他版本/翻译可能略有差异。
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "shift": ("shift", "shift (ppm)", "δ", "delta", "ppm"),
    "range": ("range", "ranges"),
    "h_count": ("h's", "h", "hs", "h count", "n h"),
    "integral": ("integral", "integration"),
    "class": ("class", "multiplicity", "mult"),
    "j": ("j's", "j", "j (hz)", "j hz", "coupling", "j coupling"),
    "name": ("name", "id", "multiplet"),
}

_ALL_COLUMN_KEYWORDS: frozenset[str] = frozenset(
    alias for aliases in _COLUMN_ALIASES.values() for alias in aliases
)


class NMRPeak(BaseModel):
    """一行 multiplet 数据。`shift_ppm` 是峰中心，`shift_range` 是 multiplet 区间。

    `integration` 优先取 "H's"（取整氢数），缺则用 "Integral"（相对原值）；
    `j_hz` 从 "J's" 列拆，多 J 用任意非数字字符分隔；
    `assignment` 第一版填 MestReNova 内部字母 ID（F/E/D/...），Phase 8 会做
    到结构原子编号的映射。
    """

    shift_ppm: float
    shift_range: tuple[float, float] | None = None
    integration: float | None = None
    multiplicity: str | None = None
    j_hz: list[float] = Field(default_factory=list)
    assignment: str | None = None
    note: str | None = None


class NMRSpectrum(BaseModel):
    """一张谱图：核 / 频率 / 溶剂 + 峰列表。

    `frequency_mhz` 和 `solvent` 不在 multiplet 表里，需 CLI 显式传或上游补。
    """

    nucleus: Literal["1H", "13C", "19F", "31P"] = "1H"
    frequency_mhz: float | None = None
    solvent: str | None = None
    sample_id: str | None = None
    peaks: list[NMRPeak]


def normalize_multiplicity(raw: str | None) -> str:
    """把 'singlet' / 'doublet of doublets' 等长名映射成标准缩写 s/d/dd/...

    未匹配 alias 时按 lowercase + strip 返回原值。空输入返回空字符串。"""
    if raw is None:
        return ""
    s = str(raw).strip().lower()
    if not s:
        return ""
    return _MULT_ALIASES.get(s, s)


def parse_j_values(raw: str | None) -> list[float]:
    """把 J 字段拆成 list[float]。

    支持：'97.06' / '8.0, 2.0' / 'J = 8.0 Hz' / 'J1 = 8.0, J2 = 2.0 Hz' / '' / None。
    "J1=" / "J2=" 等前缀以及 "Hz" 单位会先去掉，避免把下标 1/2 当成数值。"""
    if not raw:
        return []
    text = str(raw).strip()
    if not text:
        return []
    cleaned = _J_PREFIX_RE.sub("", text)
    cleaned = _HZ_SUFFIX_RE.sub("", cleaned)
    return [float(m) for m in _NUMBER_RE.findall(cleaned)]


def parse_shift_range(raw: str | None) -> tuple[float, float] | None:
    """把 '8.86 .. 8.29' / '7.80–7.23' 等区间拆成 (low, high)。

    MestReNova 习惯从高到低写，但返回前会排序成 (low, high) 保持单调。
    数字不足 2 个返回 None。"""
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    numbers = _NUMBER_RE.findall(text)
    if len(numbers) < 2:
        return None
    a, b = float(numbers[0]), float(numbers[1])
    return (min(a, b), max(a, b))


def _resolve_column(row: dict[str, str], aliases: tuple[str, ...]) -> str:
    """按列名别名（大小写不敏感）找列值。找不到返回空串。"""
    for key, value in row.items():
        if key.strip().lower() in aliases:
            return value
    return ""


def _parse_optional_float(raw: str) -> float | None:
    s = raw.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _row_to_peak(row: dict[str, str]) -> NMRPeak:
    shift_raw = _resolve_column(row, _COLUMN_ALIASES["shift"]).strip()
    if not shift_raw:
        raise NMRInputError(f"行缺少 Shift 列：{row!r}")
    try:
        shift_ppm = float(shift_raw)
    except ValueError as e:
        raise NMRInputError(
            f"Shift 非数值：{shift_raw!r}。"
            f" 检查 MestReNova 导出是否选了正确的列分隔符（应为 Tab）。"
        ) from e

    shift_range = parse_shift_range(_resolve_column(row, _COLUMN_ALIASES["range"]))

    h_count = _parse_optional_float(_resolve_column(row, _COLUMN_ALIASES["h_count"]))
    integral = _parse_optional_float(_resolve_column(row, _COLUMN_ALIASES["integral"]))
    integration = h_count if h_count is not None else integral

    class_raw = _resolve_column(row, _COLUMN_ALIASES["class"])
    multiplicity = normalize_multiplicity(class_raw)
    if multiplicity and multiplicity not in KNOWN_MULTIPLICITIES:
        warnings.warn(
            f"未识别的 multiplicity {class_raw!r}（按原值保留）", stacklevel=3
        )

    j_hz = parse_j_values(_resolve_column(row, _COLUMN_ALIASES["j"]))

    name_raw = _resolve_column(row, _COLUMN_ALIASES["name"]).strip()
    assignment: str | None = None
    if name_raw:
        # MestReNova 习惯写 "F (s)"：取首个 token 作为 multiplet ID
        tokens = name_raw.split()
        if tokens:
            assignment = tokens[0]

    return NMRPeak(
        shift_ppm=shift_ppm,
        shift_range=shift_range,
        integration=integration,
        multiplicity=multiplicity or None,
        j_hz=j_hz,
        assignment=assignment,
    )


def _read_source(source: str | Path) -> str:
    """把 Path / 路径字符串 / 直接的文本统一成文本。

    str 输入：若不含 newline/tab 且文件存在则读文件；否则当作直接的文本块。"""
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8")
    text = str(source)
    if "\n" not in text and "\t" not in text:
        candidate = Path(text)
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return text


def _maybe_normalize_newline_layout(text: str) -> str:
    """处理 MestReNova 复制粘贴的第二种姿态：每个字段独占一行 + 空行分隔每组。

    出现条件：同学把表格复制后贴进不识别 tab 的输入框（如微信、某些 web 表单），
    tab 被替换成换行。检测到这种布局时按空行分块，每块拼成 tab-separated 一行，
    再走原 tab-sep parser。

    检测条件：第一非空行不含 tab，且其 stripped 小写匹配某列名别名。
    """
    raw_lines = text.splitlines()
    first_non_empty = next((ln for ln in raw_lines if ln.strip()), None)
    if first_non_empty is None:
        return text
    if "\t" in first_non_empty:
        return text
    if first_non_empty.strip().lower() not in _ALL_COLUMN_KEYWORDS:
        return text

    # 表头：连续的列名行（每行单字段、都匹配 _ALL_COLUMN_KEYWORDS）；遇空行或
    # 非列名行立刻结束。这一步把表头从数据中分离出来——它们之间没有空行隔开。
    header: list[str] = []
    i = 0
    while i < len(raw_lines):
        ln = raw_lines[i].strip()
        if not ln:
            if header:
                break
            i += 1
            continue
        if ln.lower() in _ALL_COLUMN_KEYWORDS:
            header.append(ln)
            i += 1
        else:
            break

    if not header:
        return text

    # 数据组：每组连续的非空行，空行分隔
    groups: list[list[str]] = []
    current: list[str] = []
    while i < len(raw_lines):
        ln = raw_lines[i].strip()
        if ln:
            current.append(ln)
        elif current:
            groups.append(current)
            current = []
        i += 1
    if current:
        groups.append(current)

    if not groups:
        return text  # 表头之后没数据；让下游报"表为空"
    return "\n".join(["\t".join(header), *("\t".join(g) for g in groups)])


def _split_table(text: str) -> list[dict[str, str]]:
    """切 multiplet 表：找含 'Shift' 的表头行，下面每行按 tab split 并对齐到表头。

    缺尾列（如单峰时 J's 空）会被 pad 成空串；多余列截断。"""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    header_idx = next(
        (i for i, ln in enumerate(lines) if "shift" in ln.lower()), None
    )
    if header_idx is None:
        raise NMRInputError(
            "找不到 multiplet 表头：期望某一行包含 'Shift' 列。"
            f" 收到 {len(lines)} 行，首行：{lines[0][:80]!r}"
        )
    header = [h.strip() for h in lines[header_idx].split("\t")]
    if len(header) < 3:
        raise NMRInputError(
            f"表头列数过少 ({len(header)})；可能不是 Tab 分隔。"
            f" 在 MestReNova 里复制 multiplet 表时请确保用 Tab 而非空格分隔。"
        )

    raw_rows = [line.split("\t") for line in lines[header_idx + 1:]]

    # MestReNova 复制粘贴有两种"行号列"quirk，按首行模式判断：
    #   (a) 数据行比表头多 1 列、首字段是行号  → 丢首列
    #   (b) 数据行与表头等列、首字段是行号、表头第一列不是 Shift 别名
    #        → 同学漏复制了表头第一个 tab，给表头补一个虚 "#" 列
    if raw_rows and raw_rows[0] and raw_rows[0][0].strip().isdigit():
        first_len = len(raw_rows[0])
        header_first_is_shift = header[0].strip().lower() in _COLUMN_ALIASES["shift"]
        if first_len == len(header) + 1:
            raw_rows = [r[1:] for r in raw_rows]
        elif first_len == len(header) and not header_first_is_shift:
            header = ["#", *header]

    rows: list[dict[str, str]] = []
    for fields in raw_rows:
        if len(fields) < len(header):
            fields = fields + [""] * (len(header) - len(fields))
        else:
            fields = fields[: len(header)]
        rows.append(dict(zip(header, fields, strict=True)))
    return rows


def parse_mestrenova_multiplet_table(
    source: str | Path,
    *,
    nucleus: Literal["1H", "13C", "19F", "31P"] = "1H",
    frequency_mhz: float | None = None,
    solvent: str | None = None,
    sample_id: str | None = None,
) -> NMRSpectrum:
    """解析 MestReNova multiplet 表（tab-separated）成 `NMRSpectrum`。

    `source` 可以是文件路径或直接的文本块；前者会被自动 read_text。
    `nucleus / frequency_mhz / solvent / sample_id` 由 CLI 补，表本身不带。
    """
    text = _read_source(source)
    text = _maybe_normalize_newline_layout(text)
    rows = _split_table(text)
    if not rows:
        raise NMRInputError("multiplet 表为空（找到表头但下面没有数据行）")
    peaks = [_row_to_peak(r) for r in rows]
    return NMRSpectrum(
        nucleus=nucleus,
        frequency_mhz=frequency_mhz,
        solvent=solvent,
        sample_id=sample_id,
        peaks=peaks,
    )
