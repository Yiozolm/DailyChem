"""Prompting, parsing, and conservative mapping for GLM-OCR output."""

from __future__ import annotations

import json
import re
from typing import Any

from chem_workflow.ocr.client import GLMOCRClient, OCRClientError, OCRImage
from chem_workflow.ocr.models import OCRRecordDraft

OCR_PROMPT = """你是化学实验记录 OCR 助手。请阅读所有图片中的实验记录，只提取图片中明确出现的内容。

严格要求：
1. 只输出一个 JSON object，不要 Markdown 代码围栏、解释或额外文字。
2. 不要推测、补全或纠正任何数字、单位、化学式、产率或实验条件。
3. 无法确认的值使用 null，并把原因写入 warnings。
4. 每个字段尽量提供 source_text，引用照片中的原文片段。
5. starting_materials 和 reagents 使用 name/amount/source_text 对象数组。
6. raw_text 保留按图片顺序整理的 OCR 原文；无法映射到字段的内容放入 unmapped_text。

JSON 结构：
{
  "compound_id": {"value": null, "source_text": null},
  "product_name": {"value": null, "source_text": null},
  "smiles": {"value": null, "source_text": null},
  "starting_materials": [{
    "name": {"value": null, "source_text": null},
    "amount": {"value": null, "source_text": null},
    "source_text": null
  }],
  "reagents": [],
  "solvent": {"value": null, "source_text": null},
  "temperature": {"value": null, "source_text": null},
  "time": {"value": null, "source_text": null},
  "workup": {"value": null, "source_text": null},
  "purification": {"value": null, "source_text": null},
  "appearance": {"value": null, "source_text": null},
  "yield_mass": {"value": null, "source_text": null},
  "yield_percent": {"value": null, "source_text": null},
  "h1_nmr": {"value": null, "source_text": null},
  "c13_nmr": {"value": null, "source_text": null},
  "hrms": {"value": null, "source_text": null},
  "ms": {"value": null, "source_text": null},
  "ir": {"value": null, "source_text": null},
  "uv": {"value": null, "source_text": null},
  "raw_text": "",
  "unmapped_text": [],
  "warnings": []
}
"""


class OCRServiceError(RuntimeError):
    """Raised when the OCR response cannot be converted into a safe draft."""


class OCRService:
    """Use a local GLM-OCR client and validate its result into a draft."""

    def __init__(self, client: GLMOCRClient) -> None:
        self.client = client

    def recognize(self, images: list[OCRImage]) -> tuple[OCRRecordDraft, dict[str, object], str]:
        """Return structured draft, raw response, and raw model content."""
        try:
            raw_response = self.client.recognize(images, OCR_PROMPT)
            content = self.client.extract_content(raw_response)
        except OCRClientError as error:
            raise OCRServiceError(str(error)) from error
        draft = parse_ocr_content(content, page_count=len(images))
        return draft, raw_response, content


def parse_ocr_content(content: str, *, page_count: int = 1) -> OCRRecordDraft:
    """Parse fenced or plain JSON while rejecting non-object model output."""
    try:
        payload = _extract_json(content)
        normalized = _normalize_payload(payload)
        normalized["page_count"] = page_count
        return OCRRecordDraft.model_validate(normalized)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise OCRServiceError(f"GLM-OCR 输出无法解析为结构化记录：{error}") from error


def _extract_json(content: str) -> dict[str, Any]:
    stripped = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced else stripped
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("未找到 JSON object")
        candidate = candidate[start : end + 1]
    payload = json.loads(candidate)
    if not isinstance(payload, dict):
        raise ValueError("JSON 顶层必须是 object")
    return payload


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
        normalized[name] = _coerce_field(payload.get(name))
    normalized["starting_materials"] = _coerce_materials(payload.get("starting_materials"))
    normalized["reagents"] = _coerce_materials(payload.get("reagents"))
    normalized["raw_text"] = str(payload.get("raw_text") or payload.get("text") or "")
    normalized["unmapped_text"] = _string_list(payload.get("unmapped_text"))
    normalized["warnings"] = _string_list(payload.get("warnings"))
    return normalized


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


__all__ = ["OCRService", "OCRServiceError", "OCR_PROMPT", "parse_ocr_content"]
