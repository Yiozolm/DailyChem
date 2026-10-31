"""Turn a plain GLM-OCR page transcription into a review-required record draft.

GLM-OCR reads handwriting well when asked for plain text, but it is a small model and is
unreliable at filling a large JSON schema. Field mapping therefore happens here, with
deterministic rules that keep every value traceable to a transcribed line.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from chem_workflow.ocr.models import OCRRecordDraft, OCRTableRow
from chem_workflow.ocr.normalization import _known_material_role, _normalize_payload
from chem_workflow.ocr.stoichiometry import (
    QUANTITY_PATTERN,
    check_material_table,
    check_yield,
    parse_number,
    parse_quantity,
)

# --- LaTeX cleanup -------------------------------------------------------------------------

_LATEX_SYMBOLS = (
    (r"\\mu\b\s?", "μ"),
    (r"\^\s*\{?\s*\\circ\s*\}?", "°"),
    (r"\\circ\b", "°"),
    (r"\\%", "%"),
    (r"\\(?:right|long|longright)arrow\b|\\to\b", "→"),
    (r"\\cdot\b", "·"),
    (r"\\times\b", "×"),
)
_LATEX_WRAPPERS = re.compile(r"\\(?:text|mathrm|mathbf|textrm|rm)\s*\{([^{}]*)\}")
_LATEX_GROUPED_SCRIPT = re.compile(r"[_^]\{([^{}]*)\}")
_LATEX_ARROW = re.compile(r"\\xrightarrow\s*\{([^{}]*)\}")


def clean_transcript(text: str) -> str:
    """Normalize Unicode (µ, ℃, subscripts) and strip GLM-OCR's inline LaTeX."""
    text = unicodedata.normalize("NFKC", text)
    for pattern, replacement in _LATEX_SYMBOLS:
        text = re.sub(pattern, replacement, text)
    previous = None
    while previous != text:
        previous = text
        text = _LATEX_WRAPPERS.sub(r"\1", text)
        text = _LATEX_GROUPED_SCRIPT.sub(r"\1", text)
        text = _LATEX_ARROW.sub(r" → \1 → ", text)
    text = re.sub(r"[_^](\w)", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = text.replace("$", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(lines).strip()


# --- Reagent table -------------------------------------------------------------------------

_PERCENT_SUFFIX = r"(?:\s*\(\s*\d+(?:\.\d+)?\s*%\s*\))?"
_VALUE_TOKEN = re.compile(
    rf"(?P<quantity>{QUANTITY_PATTERN.pattern}{_PERCENT_SUFFIX})"
    r"|(?P<drop>\d+\s*drops?\b)"
    r"|(?P<bare>(?<![\w.])\d+(?:\.\d+)?(?![\w°%:/]|\.\d))",
    flags=re.I,
)
_COLUMN_WORDS = {
    "compound": "name",
    "name": "name",
    "reagent": "name",
    "m": None,  # ambiguous between M and m; resolved by case below
    "mw": "molar_mass",
    "eq": "equivalents",
    "equiv": "equivalents",
    "ef": "equivalents",
    "eb": "equivalents",
    "n": "amount",
    "v": "volume",
    "d": "density",
    "note": "note",
}
_NAME_STOPWORDS = {"the", "to", "of", "with", "and", "on", "by", "in", "page", "signed", "date"}
_NUMERIC_COLUMNS = ("molar_mass", "equivalents", "density")


@dataclass
class _Table:
    rows: list[OCRTableRow] = field(default_factory=list)
    start: int | None = None
    end: int = 0
    warnings: list[str] = field(default_factory=list)


def parse_material_table(text: str) -> tuple[list[OCRTableRow], list[str]]:
    """Parse the first reagent table in a cleaned transcript."""
    table = _find_table(text.splitlines())
    return table.rows, table.warnings


def _find_table(lines: list[str]) -> _Table:
    markdown = _parse_markdown_table(lines)
    if markdown.rows:
        return markdown
    return _parse_whitespace_table(lines)


def _parse_markdown_table(lines: list[str]) -> _Table:
    table = _Table()
    start = next((i for i, line in enumerate(lines) if line.startswith("|")), None)
    if start is None:
        return table
    end = start
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    block = [
        (_split_markdown_row(line), line)
        for line in lines[start:end]
        if not re.fullmatch(r"\|[\s:|-]*\|?", line)
    ]
    if len(block) < 2:
        return table
    columns = [_column_key(cell) for cell in block[0][0]]
    for cells, line in block[1:]:
        name = cells[0].strip()
        if not name:
            continue
        fixed: dict[str, str] = {}
        token_text: list[str] = []
        for column, cell in zip(columns[1:], cells[1:], strict=False):
            if not cell:
                continue
            if column in _NUMERIC_COLUMNS:
                number = parse_number(cell)
                if number is not None:
                    fixed[column] = _number_text(cell)
                if parse_quantity(cell) is not None:
                    table.warnings.append(
                        f"{name}：{_COLUMN_LABELS[column]}列写成了“{cell}”，带有不该出现的单位，"
                        "已只取数值，请核对。"
                    )
            elif column == "note":
                fixed["note"] = cell
            else:
                token_text.append(cell)
        row, warnings = _build_row(name, " ".join(token_text), line, fixed)
        table.rows.append(row)
        table.warnings.extend(warnings)
    table.start, table.end = start, end
    return table


def _parse_whitespace_table(lines: list[str]) -> _Table:
    table = _Table()
    header = next((i for i, line in enumerate(lines) if _is_header(line)), None)
    in_table = header is not None
    index = header + 1 if header is not None else 0
    pending: tuple[str, str] | None = None

    def flush_pending() -> None:
        nonlocal pending
        if pending is not None and in_table:
            table.rows.append(OCRTableRow(name=pending[0], source_text=pending[1]))
        pending = None

    while index < len(lines):
        line = lines[index]
        if not line:
            if table.rows:
                break
            index += 1
            continue
        if line.startswith(("-", "|")):
            break
        name, values = _split_name(line)
        tokens_ok = bool(values) and _is_value_text(values)
        if name and not values and _looks_like_name(name):
            flush_pending()
            pending = (name, line)
        elif not name and tokens_ok and pending is not None:
            row, warnings = _build_row(pending[0], values, f"{pending[1]} {line}")
            table.rows.append(row)
            table.warnings.extend(warnings)
            pending = None
            in_table = True
        elif name and tokens_ok and _looks_like_name(name):
            flush_pending()
            row, warnings = _build_row(name, values, line)
            table.rows.append(row)
            table.warnings.extend(warnings)
            in_table = True
        elif in_table:
            break
        else:
            pending = None
            index += 1
            continue
        if table.start is None and in_table:
            table.start = header if header is not None else index
        table.end = index + 1
        index += 1
    flush_pending()
    if table.rows and header is not None:
        table.start = header
    return table


_COLUMN_LABELS = {"molar_mass": "M", "equivalents": "eq", "density": "d"}


def _split_markdown_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _column_key(cell: str) -> str | None:
    word = re.sub(r"[^A-Za-z]", "", cell)
    if word == "M":
        return "molar_mass"
    if word == "m":
        return "mass"
    return _COLUMN_WORDS.get(word.lower())


def _is_header(line: str) -> bool:
    words = re.findall(r"[a-z]+", line.lower())
    if not words:
        return False
    if words[0] == "compound":
        return True
    return len(words) >= 4 and all(word in _COLUMN_WORDS or word == "mass" for word in words)


def _split_name(line: str) -> tuple[str, str]:
    """Split ``K2CO3 138.21 2.0 ...`` into the name and the value text."""
    parts = line.split(" ")
    for index, part in enumerate(parts):
        if re.match(r"\d", part):
            return " ".join(parts[:index]).strip(" .,:"), " ".join(parts[index:])
    return line.strip(" .,:"), ""


def _is_value_text(text: str) -> bool:
    leftover = _VALUE_TOKEN.sub(" ", text)
    return bool(_VALUE_TOKEN.search(text)) and not re.search(r"[A-Za-z0-9°%]", leftover)


def _looks_like_name(name: str) -> bool:
    words = name.split()
    return (
        0 < len(words) <= 3
        and len(name) <= 30
        and not any(word.lower() in _NAME_STOPWORDS for word in words)
        and all(re.fullmatch(r"[A-Za-z0-9()+'.,\-]+", word) for word in words)
    )


def _build_row(
    name: str, values: str, source: str, fixed: dict[str, str] | None = None
) -> tuple[OCRTableRow, list[str]]:
    fields: dict[str, str] = dict(fixed or {})
    bare: list[str] = []
    extras: list[str] = []
    for match in _VALUE_TOKEN.finditer(values):
        if match.group("bare"):
            bare.append(match.group("bare"))
            continue
        if match.group("drop"):
            slot, display = "volume", re.sub(r"\s+", " ", match.group("drop"))
        else:
            text = match.group("quantity")
            quantity = parse_quantity(text)
            if quantity is None:
                continue
            slot = quantity.kind
            percent = re.search(r"\(\s*\d+(?:\.\d+)?\s*%\s*\)", text)
            display = quantity.display() + (f" {percent.group(0)}" if percent else "")
        if slot in fields:
            extras.append(display)
        else:
            fields[slot] = display
    free_columns = [column for column in _NUMERIC_COLUMNS if column not in fields]
    for column, value in zip(free_columns, bare, strict=False):
        fields[column] = value
    extras.extend(bare[len(free_columns) :])
    warnings: list[str] = []
    if extras:
        extra_text = "、".join(extras)
        note = fields.get("note")
        fields["note"] = f"{note}; {extra_text}" if note else extra_text
        warnings.append(f"{name} 行有多余数值 {extra_text}，可能属于相邻行，请对照照片核对。")
    return OCRTableRow(name=name, source_text=source, **fields), warnings


def _number_text(cell: str) -> str:
    match = re.search(r"\d+(?:\.\d+)?", cell)
    return match.group(0) if match else cell


# --- Body text -----------------------------------------------------------------------------

_BOILERPLATE = re.compile(
    r"^(?:continued\b|read and understood|signed\b|date\b|project\b)"
    r"|^\d{1,2}/\d{1,2}/\d{2,4}$|^\d{6,}$",
    flags=re.I,
)
_SENTENCE_START = (
    r"(?:Add|Added|Quench|Extract|Wash|Dry|Dried|Evaporate|Remove|Load|Run|Re-?\s?crystalli[sz]e"
    r"|Filter|Concentrate|Stir|Heat|Cool|Dissolve|The|Then|TLC|Colou?r|Yield|Column|NMR|MS|May"
    r"|After|Purif\w*)"
)
_SENTENCE_SPLIT = re.compile(rf"(?<=[.;])\s+(?={_SENTENCE_START}\b)")
_YIELD = re.compile(r"\byield\b", flags=re.I)
_NOTE = re.compile(
    r"\b(?:nmr|ms showed|may be|may because|decompos\w*|incorrect|not clear)\b", flags=re.I
)
_PURIFICATION = re.compile(
    r"column|re-?\s?crystalli|chromatograph|silica|normal phase|reverse phase|prep-?tlc"
    r"|\d+(?:\.\d+)?\s*(?:-\s*\d+(?:\.\d+)?\s*)?%\s*\w+(?:\s+in\s+\w+)?",
    flags=re.I,
)
_WORKUP = re.compile(
    r"quench|extract|wash|brine|\bdr(?:y|ied)\b|evaporat|rotovap|rot\s*o?\s*to\s*vape"
    r"|remov\w*\s+(?:the\s+)?solvent|concentrat\w*\s+(?:in\s+vacuo|under|on|to)|filter",
    flags=re.I,
)
_TEMPERATURE = re.compile(r"(-?\d+(?:\.\d+)?)\s*°\s*C?", flags=re.I)
_ROOM_TEMPERATURE = re.compile(r"\b(?:rt|r\.t\.|room temperature)\b", flags=re.I)
_TIME = re.compile(r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hours|min)\b", flags=re.I)
_PERCENT = re.compile(r"\d+(?:\.\d+)?\s*%")
_OBTAINED_MASS = re.compile(
    rf"\bobtain(?:ed)?\s+(?:\D{{0,6}}?)({QUANTITY_PATTERN.pattern})", flags=re.I
)
_APPEARANCE = re.compile(
    r"\b(?:(?:pale|light|dark|off)[\s-])?"
    r"(?:white|colou?rless|yellow|orange|red|brown|black|green|blue|purple|pink|tan)"
    r"(?:\s+[\w-]+){0,2}?\s+(?:solid|oil|powder|crystals?|foam|gum|needles?)\b(?!-)",
    flags=re.I,
)


@dataclass
class _Sections:
    procedure: list[str] = field(default_factory=list)
    workup: list[str] = field(default_factory=list)
    purification: list[str] = field(default_factory=list)
    yield_sentences: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _split_sections(lines: list[str]) -> _Sections:
    sections = _Sections()
    for raw_line in lines:
        line = raw_line.lstrip("-• ").strip()
        if not line or _BOILERPLATE.search(line) or "→" in line:
            continue
        procedure_parts: list[str] = []
        for sentence in _SENTENCE_SPLIT.split(line):
            if _YIELD.search(sentence):
                sections.yield_sentences.append(sentence)
            elif _NOTE.search(sentence):
                sections.notes.append(sentence)
            elif _PURIFICATION.search(sentence):
                sections.purification.append(sentence)
            elif _WORKUP.search(sentence):
                sections.workup.append(sentence)
            else:
                procedure_parts.append(sentence)
        if procedure_parts:
            sections.procedure.append(" ".join(procedure_parts))
    return sections


# --- Draft assembly ------------------------------------------------------------------------


def draft_from_transcript(
    text: str, *, page_count: int = 1, warnings: list[str] | None = None
) -> OCRRecordDraft:
    """Build a review-required draft from plain page transcriptions."""
    cleaned = clean_transcript(text)
    lines = cleaned.splitlines()
    table = _find_table(lines)
    if table.rows and table.start is not None:
        scheme_lines = lines[: table.start]
        body_lines = lines[table.end :]
    else:
        scheme_lines = [line for line in lines if "→" in line]
        body_lines = lines
    sections = _split_sections(body_lines)
    scheme_text = "\n".join(scheme_lines)
    procedure_text = "\n".join(sections.procedure)
    all_sentences = [
        *sections.procedure,
        *sections.workup,
        *sections.purification,
        *sections.yield_sentences,
    ]

    starting, reagents, solvents, unmapped = _materials_from_rows(table.rows)
    yield_mass, yield_percent = _yield_values(sections.yield_sentences, all_sentences)
    payload: dict[str, Any] = {
        "procedure": _field(procedure_text),
        "workup": _field(" ".join(sections.workup)),
        "purification": _field(" ".join(sections.purification)),
        "solvent": _field(", ".join(solvents)),
        "temperature": _first_match_field(
            [procedure_text, scheme_text], _TEMPERATURE, lambda m: f"{m.group(1)} °C"
        )
        or _first_match_field([procedure_text, scheme_text], _ROOM_TEMPERATURE, lambda m: "rt"),
        "time": _first_match_field(
            [scheme_text], _TIME, lambda m: f"{m.group(1)} {m.group(2).lower()}"
        ),
        "appearance": _first_match_field(all_sentences, _APPEARANCE, lambda m: m.group(0)),
        "yield_mass": yield_mass,
        "yield_percent": yield_percent,
        "starting_materials": starting,
        "reagents": reagents,
        "raw_text": cleaned,
        "unmapped_text": [*unmapped, *sections.notes],
        "warnings": [*(warnings or []), *table.warnings],
    }
    normalized = _normalize_payload(payload, recover_materials=not table.rows)
    normalized["material_table"] = [row.model_dump() for row in table.rows]
    normalized["page_count"] = page_count
    draft = OCRRecordDraft.model_validate(normalized)

    checks = [
        *check_material_table(draft.material_table),
        *check_yield(draft.material_table, draft.yield_mass.value, draft.yield_percent.value),
    ]
    if not table.rows:
        checks.append("未识别到试剂表（Compound / M / eq / n / m / V / d），请手动填写用量。")
    if checks:
        draft = draft.model_copy(update={"warnings": [*draft.warnings, *checks]})
    return draft


def _materials_from_rows(
    rows: list[OCRTableRow],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    starting: list[dict[str, Any]] = []
    reagents: list[dict[str, Any]] = []
    solvents: list[str] = []
    unmapped: list[str] = []
    for row in rows:
        role = _known_material_role(row.name)
        has_amount = any((row.molar_mass, row.mass, row.amount))
        if role is None:
            if row.volume and not has_amount:
                role = "solvent"
            else:
                equivalents = parse_number(row.equivalents)
                role = "starting" if equivalents == 1.0 and not starting else "reagent"
        if role == "ignore":
            unmapped.append(row.source_text or row.name)
        elif role == "solvent":
            solvents.append(f"{row.name} ({row.volume})" if row.volume else row.name)
        else:
            material = {
                "name": {"value": row.name, "source_text": row.source_text},
                "amount": {"value": _amount_text(row), "source_text": row.source_text},
                "source_text": row.source_text,
            }
            (starting if role == "starting" else reagents).append(material)
    return starting, reagents, solvents, unmapped


def _amount_text(row: OCRTableRow) -> str | None:
    parts = [row.mass, row.volume, row.amount]
    if row.equivalents:
        parts.append(f"{row.equivalents} equiv")
    text = ", ".join(part for part in parts if part)
    return text or None


def _yield_values(
    yield_sentences: list[str], all_sentences: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    mass: dict[str, Any] = _field(None)
    percent: dict[str, Any] = _field(None)
    for sentence in yield_sentences:
        quantity = parse_quantity(sentence)
        if mass["value"] is None and quantity is not None and quantity.kind == "mass":
            mass = _field(quantity.display(), sentence)
        match = _PERCENT.search(sentence)
        if percent["value"] is None and match:
            percent = _field(match.group(0).replace(" ", ""), sentence)
    if mass["value"] is None:
        for sentence in all_sentences:
            match = _OBTAINED_MASS.search(sentence)
            quantity = parse_quantity(match.group(1)) if match else None
            if quantity is not None and quantity.kind == "mass":
                mass = _field(quantity.display(), sentence)
                break
    return mass, percent


def _first_match_field(texts: list[str], pattern: re.Pattern[str], render: Any) -> Any:
    for text in texts:
        for line in text.splitlines():
            match = pattern.search(line)
            if match:
                return _field(render(match), line)
    return None


def _field(value: str | None, source_text: str | None = None) -> dict[str, Any]:
    value = value.strip() if value else None
    return {"value": value or None, "source_text": source_text or value or None}


__all__ = ["clean_transcript", "draft_from_transcript", "parse_material_table"]
