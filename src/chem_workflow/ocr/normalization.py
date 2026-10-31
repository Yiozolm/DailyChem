"""Normalization and conservative repair for GLM-OCR payloads."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    # Some model prompts naturally produce {"record": {...}}; accept that wrapper.
    if isinstance(payload.get("record"), dict):
        payload = {**payload["record"], **{k: v for k, v in payload.items() if k != "record"}}
    reaction = payload.get("reaction")
    if isinstance(reaction, dict):
        payload = {**payload, **reaction}
    normalized: dict[str, Any] = {}
    scalar_names = (
        "compound_id",
        "product_name",
        "smiles",
        "procedure",
        "solvent",
        "temperature",
        "time",
        "workup",
        "purification",
        "appearance",
        "yield_mass",
        "yield_percent",
        "h1_nmr",
        "c13_nmr",
        "hrms",
        "ms",
        "ir",
        "uv",
    )
    for name in scalar_names:
        value = payload.get(name)
        if value is None and name == "procedure":
            value = payload.get("reaction_procedure", payload.get("steps"))
        normalized[name] = _coerce_field(value)
    starting_value = payload.get("starting_materials")
    if starting_value is None:
        starting_value = payload.get("starting_material")
    reagent_value = payload.get("reagents")
    if reagent_value is None:
        reagent_value = payload.get("reagent")
    normalized["starting_materials"] = _coerce_materials(starting_value)
    normalized["reagents"] = _coerce_materials(reagent_value)
    normalized["raw_text"] = str(payload.get("raw_text") or payload.get("text") or "")
    normalized["unmapped_text"] = _string_list(payload.get("unmapped_text"))
    normalized["warnings"] = _string_list(payload.get("warnings"))
    _repair_scalar_fields(normalized)
    _fill_procedure_from_raw_text(normalized)
    _repair_material_roles(normalized)
    _ensure_labelled_materials(normalized)
    _ensure_known_reagents(normalized)
    _fill_conditions_from_raw_text(normalized)
    _fill_workup_and_purification_from_raw_text(normalized)
    _repair_yield_fields(normalized)
    return normalized


_KNOWN_REAGENT_DISPLAY = {
    "k2co3": "K2CO3",
    "mei": "MeI",
    "dbu": "DBU",
    "cui": "CuI",
    "cucl2": "CuCl2",
    "agno3": "AgNO3",
    "nbs": "NBS",
    "hcl": "HCl",
    "h2so4": "H2SO4",
    "et2noh": "Et2NOH",
    "et3noh": "Et3NOH",
}


def _repair_scalar_fields(normalized: dict[str, Any]) -> None:
    """Clear table values that the model incorrectly mapped to scalar fields."""

    compound_id = normalized.get("compound_id")
    if (
        isinstance(compound_id, dict)
        and compound_id.get("value")
        and re.fullmatch(r"\d+(?:\.\d+)?", str(compound_id["value"]).strip())
    ):
        compound_id["value"] = None
        normalized.setdefault("warnings", []).append(
            "compound_id 读到了分子量等表格数字，已清空并保留待人工核对。"
        )

    product_name = normalized.get("product_name")
    if isinstance(product_name, dict) and product_name.get("value"):
        value = str(product_name["value"]).strip()
        if _known_material_role(value) in {"starting", "reagent", "solvent", "ignore"}:
            product_name["value"] = None
            normalized.setdefault("warnings", []).append(
                "product_name 读到了试剂或底物标签，已清空并保留待人工核对。"
            )

    smiles = normalized.get("smiles")
    if (
        isinstance(smiles, dict)
        and smiles.get("value")
        and any(char.isspace() for char in str(smiles["value"]))
    ):
        smiles["value"] = None
        normalized.setdefault("warnings", []).append(
            "smiles 读到了实验表格文本，已清空并保留待人工核对。"
        )


def _all_ocr_text(normalized: dict[str, Any]) -> str:
    procedure = normalized.get("procedure")
    procedure_text = procedure.get("value") if isinstance(procedure, dict) else ""
    return "\n".join(
        [
            str(normalized.get("raw_text") or ""),
            str(procedure_text or ""),
            *[str(item) for item in normalized.get("unmapped_text", [])],
        ]
    )


def _ensure_labelled_materials(normalized: dict[str, Any]) -> None:
    """Recover explicit I/II-style substrate labels from the transcription."""

    materials = normalized.get("starting_materials", [])
    if not isinstance(materials, list):
        return
    existing = {_material_key(_material_name(item)) for item in materials}
    lines = [line.strip() for line in _all_ocr_text(normalized).splitlines() if line.strip()]
    for index, line in enumerate(lines):
        match = re.fullmatch(r"(?:compound\s*[.:_-]?\s*)?([ivx]{1,4})", line, flags=re.I)
        if match is None:
            match = re.match(
                r"(?:compound\s*[.:_-]?\s*)?([ivx]{1,4})\s+\d", line, flags=re.I
            )
        if match is None:
            continue
        label = match.group(1).upper()
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if not re.search(r"\d", line + next_line):
            continue
        key = _material_key(label)
        if key in existing:
            continue
        materials.append(
            {
                "name": _coerce_field(label),
                "amount": _coerce_field(None),
                "source_text": " ".join(part for part in (line, next_line) if part),
                "status": "needs_review",
            }
        )
        existing.add(key)
        normalized.setdefault("warnings", []).append(
            f"根据逐行转录保留底物标签 {label}，请人工核对。"
        )


def _ensure_known_reagents(normalized: dict[str, Any]) -> None:
    """Add explicit reagent names present in text when the model omitted the row."""

    reagent_items = normalized.get("reagents", [])
    starting_items = normalized.get("starting_materials", [])
    if not isinstance(reagent_items, list) or not isinstance(starting_items, list):
        return
    known = {_material_key(_material_name(item)) for item in (*reagent_items, *starting_items)}
    text_key = _material_key(_all_ocr_text(normalized))
    for key, display in _KNOWN_REAGENT_DISPLAY.items():
        if key not in text_key or key in known:
            continue
        reagent_items.append(
            {
                "name": _coerce_field(display),
                "amount": _coerce_field(None),
                "source_text": _all_ocr_text(normalized),
                "status": "needs_review",
            }
        )
        known.add(key)


def _fill_conditions_from_raw_text(normalized: dict[str, Any]) -> None:
    text = _all_ocr_text(normalized)
    temperature = normalized.get("temperature")
    if isinstance(temperature, dict) and not temperature.get("value"):
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*°?\s*C\b", text, flags=re.I)
        if match:
            temperature["value"] = f"{match.group(1)} °C"
            temperature["source_text"] = match.group(0)
    time = normalized.get("time")
    if isinstance(time, dict) and not time.get("value"):
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hours)\b", text, flags=re.I)
        if match:
            time["value"] = f"{match.group(1)} h"
            time["source_text"] = match.group(0)


def _fill_workup_and_purification_from_raw_text(normalized: dict[str, Any]) -> None:
    raw_text = str(normalized.get("raw_text") or "")
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    workup_lines = [
        line for line in lines if any(
            term in line.lower()
            for term in ("quench", "extract", "wash", "brine", "dry", "rotovap", "remove solvent")
        )
    ]
    purification_lines = [
        line for line in lines if any(
            term in line.lower() for term in ("column", "recrystall", "normal phase", "silica")
        )
    ]
    _fill_text_field_from_lines(normalized, "workup", workup_lines, _is_generic_workup)
    _fill_text_field_from_lines(
        normalized, "purification", purification_lines, _is_generic_purification
    )


def _fill_text_field_from_lines(
    normalized: dict[str, Any], name: str, lines: list[str], is_generic: Any
) -> None:
    field = normalized.get(name)
    if not isinstance(field, dict) or not lines:
        return
    if field.get("value") and not is_generic(str(field["value"])):
        return
    value = " ".join(lines)
    field["value"] = value
    field["source_text"] = value


def _is_generic_workup(value: str) -> bool:
    return "quench" in value.lower() and "extraction" in value.lower()


def _is_generic_purification(value: str) -> bool:
    lowered = value.lower()
    return "column chromatography" in lowered and "recrystall" in lowered


def _repair_yield_fields(normalized: dict[str, Any]) -> None:
    mass = normalized.get("yield_mass")
    percent = normalized.get("yield_percent")
    if not isinstance(mass, dict) or not isinstance(percent, dict):
        return
    if mass.get("value") and not percent.get("value"):
        text = str(mass["value"])
        percent_match = re.search(r"(\d+(?:\.\d+)?\s*%)", text)
        if percent_match:
            percent["value"] = percent_match.group(1)
            percent["source_text"] = text
            cleaned = re.sub(r"\s*\(?\d+(?:\.\d+)?\s*%\)?", "", text).strip()
            mass["value"] = cleaned or None
    text = str(normalized.get("raw_text") or "")
    match = re.search(r"\byield\s*:?\s*([^\n]+)", text, flags=re.I)
    if not match:
        return
    line = match.group(0).strip()
    if not mass.get("value"):
        mass_match = re.search(r"(\d+(?:\.\d+)?\s*(?:mg|g|μg))", line, flags=re.I)
        if mass_match:
            mass["value"] = mass_match.group(1)
            mass["source_text"] = line
    if not percent.get("value"):
        percent_match = re.search(r"(\d+(?:\.\d+)?\s*%)", line)
        if percent_match:
            percent["value"] = percent_match.group(1)
            percent["source_text"] = line

# These are deliberately narrow and only repair a role error that is unambiguous in a
# chemistry record.  They are a safety net for model output, not a replacement for review.
_KNOWN_REAGENTS = {
    "k2co3",
    "potassiumcarbonate",
    "na2co3",
    "sodiumcarbonate",
    "cs2co3",
    "cesiumcarbonate",
    "li2co3",
    "lithiumcarbonate",
    "mei",
    "methyl iodide",
    "triethylamine",
    "et3n",
    "pyridine",
    "dbu",
    "cui",
    "cucl",
    "cucl2",
    "cubr",
    "agno3",
    "silvernitrate",
    "nbs",
    "hcl",
    "hydrochloricacid",
    "h2so4",
    "sulfuricacid",
    "naoh",
    "koh",
    "et2noh",
    "et3noh",
}
_KNOWN_SOLVENTS = {
    "dmf",
    "dichloromethane",
    "dcm",
    "thf",
    "tetrahydrofuran",
    "acetonitrile",
    "mecn",
    "acetone",
    "aceton",
    "meoh",
    "methanol",
    "toluene",
    "1,4-dioxane",
    "dioxane",
}
_PROCEDURE_TERMS = (
    "add",
    "dissolve",
    "stir",
    "heat",
    "tlc",
    "mixture",
    "solution",
)
_NON_PROCEDURE_TERMS = (
    "quench",
    "extract",
    "wash",
    "dry",
    "column",
    "recrystall",
    "yield",
)


def _fill_procedure_from_raw_text(normalized: dict[str, Any]) -> None:
    """Keep reaction-operation lines visible if the model omitted ``procedure``."""

    procedure = normalized.get("procedure")
    if not isinstance(procedure, dict) or procedure.get("value"):
        return
    raw_text = str(normalized.get("raw_text") or "")
    selected: list[str] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if (
            line
            and any(term in lowered for term in _PROCEDURE_TERMS)
            and not any(term in lowered for term in _NON_PROCEDURE_TERMS)
        ):
            selected.append(line)
    if not selected:
        return
    value = "\n".join(selected)
    normalized["procedure"] = {
        "value": value,
        "source_text": value,
        "status": "needs_review",
        "warnings": [],
    }
    normalized.setdefault("warnings", []).append(
        "模型未单独返回 procedure；已从 raw_text 中保留疑似反应操作行，请人工核对。"
    )


def _repair_material_roles(normalized: dict[str, Any]) -> None:
    """Repair obvious material-role mistakes while retaining a review warning.

    Vision models often read the first chemical row correctly but attach it to the
    ``starting_materials`` key without understanding the reaction scheme.  Moving a
    well-known base/reagent/solvent back to its proper field prevents the common
    ``K2CO3``-as-substrate failure.  Unknown names are left untouched.
    """

    starting = normalized.get("starting_materials", [])
    reagents = normalized.get("reagents", [])
    if not isinstance(starting, list) or not isinstance(reagents, list):
        return

    existing_solvent = normalized.get("solvent")
    solvent_value = existing_solvent.get("value") if isinstance(existing_solvent, dict) else None
    repaired: list[dict[str, Any]] = []
    moved: list[str] = []
    for item in starting:
        name = _material_name(item)
        role = _known_material_role(name)
        if role == "ignore":
            normalized.setdefault("unmapped_text", []).append(item.get("source_text") or name)
            continue
        if role == "solvent":
            if not solvent_value:
                normalized["solvent"] = _material_field(item)
                solvent_value = normalized["solvent"].get("value")
                moved.append(f"{name} → solvent")
            else:
                normalized.setdefault("unmapped_text", []).append(
                    item.get("source_text") or name
                )
            continue
        if role == "reagent":
            if not _contains_material(reagents, name):
                reagents.append(item)
            moved.append(f"{name} → reagent")
            continue
        repaired.append(item)

    # A model may put a solvent in reagents.  Move it only when the solvent field is empty.
    kept_reagents: list[dict[str, Any]] = []
    for item in reagents:
        name = _material_name(item)
        role = _known_material_role(name)
        if role == "starting":
            if not _contains_material(repaired, name):
                repaired.append(item)
            moved.append(f"{name} → starting material")
        elif role == "ignore":
            normalized.setdefault("unmapped_text", []).append(item.get("source_text") or name)
        elif role == "solvent" and not solvent_value:
            normalized["solvent"] = _material_field(item)
            solvent_value = normalized["solvent"].get("value")
            moved.append(f"{name} → solvent")
        else:
            kept_reagents.append(item)

    normalized["starting_materials"] = repaired
    normalized["reagents"] = kept_reagents

    if not repaired:
        procedure_payload = normalized.get("procedure")
        procedure_text = (
            str(procedure_payload.get("value") or "")
            if isinstance(procedure_payload, dict)
            else ""
        )
        raw_text = "\n".join(
            [
                str(normalized.get("raw_text") or ""),
                procedure_text,
                *[str(item) for item in normalized.get("unmapped_text", [])],
            ]
        )
        inferred = _infer_labelled_starting_material(raw_text)
        if inferred is not None:
            normalized["starting_materials"] = [inferred]
            normalized.setdefault("warnings", []).append(
                "未从结构图读出底物名称；根据原文标签保留为 compound I，请人工核对。"
            )
    if moved:
        normalized.setdefault("warnings", []).append(
            "已按常见化学角色重新分类：" + "、".join(moved) + "；请人工核对。"
        )


def _material_name(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    name = item.get("name")
    if isinstance(name, dict):
        return str(name.get("value") or "").strip()
    return str(name or "").strip()


def _material_field(item: dict[str, Any]) -> dict[str, Any]:
    field = _coerce_field(item.get("name"))
    if not field.get("source_text"):
        field["source_text"] = _optional_string(item.get("source_text"))
    return field


def _material_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    normalized = normalized.translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _known_material_role(value: str) -> str | None:
    key = _material_key(value)
    if key in {"solvent", "cosolvent"}:
        return "ignore"
    if re.fullmatch(r"(?:compound)?[ivx]{1,4}", key):
        return "starting"
    if any(token in key for token in ("dmf", "mecn", "meoh")):
        return "solvent"
    if any(
        token in key
        for token in (
            "k2co3",
            "na2co3",
            "cs2co3",
            "naoh",
            "koh",
            "agno3",
            "nbs",
            "hcl",
            "h2so4",
            "cucl2",
            "et2noh",
            "et3noh",
        )
    ):
        return "reagent"
    if key in {_material_key(item) for item in _KNOWN_SOLVENTS}:
        return "solvent"
    if key in {_material_key(item) for item in _KNOWN_REAGENTS}:
        return "reagent"
    return None


def _contains_material(items: list[dict[str, Any]], name: str) -> bool:
    key = _material_key(name)
    return bool(key) and any(_material_key(_material_name(item)) == key for item in items)


def _infer_labelled_starting_material(raw_text: str) -> dict[str, Any] | None:
    """Recover a labelled substrate when the model only returned reagents.

    This intentionally returns the label, never a guessed chemical identity.
    """

    if not re.search(r"\b(?:k2co3|k₂co₃|potassium carbonate)\b", raw_text, flags=re.I):
        return None
    for line in (part.strip() for part in raw_text.splitlines() if part.strip()):
        if (
            re.search(r"\bcompound\s+i\b", line, flags=re.I)
            or re.search(r"\b(?:mixture|solution)\s+of\s+[i1]\b", line, flags=re.I)
            or (
                re.match(r"^(?:compound\s*)?[i1](?:\s|[,|:])", line, flags=re.I)
                and re.search(r"\d", line)
            )
        ):
            return {
                "name": _coerce_field("compound I"),
                "amount": _coerce_field(None),
                "source_text": line,
                "status": "needs_review",
            }
    return None


def _coerce_field(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        raw_value = value.get("value", value.get("text"))
        return {
            "value": _optional_string(raw_value),
            "source_text": _optional_string(value.get("source_text", value.get("source"))),
            "status": value.get("status", "needs_review"),
            "warnings": _string_list(value.get("warnings")),
        }
    return {"value": _optional_string(value), "status": "needs_review"}


def _coerce_materials(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    materials: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            materials.append({"name": _coerce_field(item), "amount": _coerce_field(None)})
            continue
        if not isinstance(item, dict):
            continue
        materials.append(
            {
                "name": _coerce_field(item.get("name")),
                "amount": _coerce_field(item.get("amount")),
                "source_text": _optional_string(item.get("source_text", item.get("source"))),
                "status": item.get("status", "needs_review"),
            }
        )
    return materials


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


__all__ = [
    "_is_generic_purification",
    "_is_generic_workup",
    "_normalize_payload",
]
