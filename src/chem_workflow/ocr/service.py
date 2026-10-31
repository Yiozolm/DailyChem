"""Prompting, parsing, and conservative mapping for GLM-OCR output."""

from __future__ import annotations

import json
import re
from typing import Any

from chem_workflow.ocr.client import GLMOCRClient, OCRClientError, OCRImage
from chem_workflow.ocr.models import OCRRecordDraft
from chem_workflow.ocr.normalization import (
    _is_generic_purification,
    _is_generic_workup,
    _normalize_payload,
)

OCR_PROMPT = """你是化学实验记录 OCR 助手。请阅读所有图片中的实验记录，只提取图片中明确出现的内容。

严格要求：
1. 只输出一个 JSON object，不要 Markdown 代码围栏、解释或额外文字。
2. 不要推测、补全或纠正任何数字、单位、化学式、产率或实验条件。
3. 无法确认的值使用 null，并把原因写入 warnings。
4. 每个字段尽量提供 source_text，引用照片中的原文片段。
5. 先按反应式箭头和实验表格的角色分类，再填写 starting_materials 和 reagents。
   starting_materials 只放被转化的底物（通常是反应箭头左侧或表格中标为 Compound/底物的有机项）；
   如果反应式左侧有 I、II 等多个有机底物，全部列入 starting_materials；
   reagents 放碱、酸、催化剂、活化剂和其他加入的试剂。溶剂（例如 DMF）只放入 solvent。
   不要把 K2CO3、Na2CO3、Cs2CO3、MeI、DBU、CuI、AgNO3、NBS、DMF、MeCN、EtOAc、hexane 或水
   当作 starting material。
   若底物只有结构图或标签 I，保留为“compound I”或“I”，不要猜它的化学名称；若角色无法确认，
   放入 unmapped_text 并加入 warning，而不是擅自归类。
   例如表格或步骤同时出现 I、K2CO3、MeI 和 DMF 时，应分别放入 starting_materials、reagents、
   reagents 和 solvent；I 的结构名称不可见时仍保留为 compound I。
6. procedure 记录反应设置和按时间顺序的加料、滴加、TLC/颜色观察等操作；workup 只记录淬灭、萃取、
   洗涤、干燥等后处理；purification 只记录柱层析/重结晶等纯化。
   procedure 要引用照片中的完整原文片段，不能只写“按常规操作”。raw_text 保留按图片顺序整理的全部
   OCR 原文；无法映射到字段的内容放入
   unmapped_text。

JSON 结构：
{
  "compound_id": {"value": null, "source_text": null},
  "product_name": {"value": null, "source_text": null},
  "smiles": {"value": null, "source_text": null},
  "procedure": {"value": null, "source_text": null},
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

OCR_TRANSCRIPTION_PROMPT = """Read every visible handwritten line in these chemistry notebook images
in reading order.

Return one JSON object only: {"raw_text": "full transcription of all visible text", "warnings": []}.
Do not summarize or omit timestamped lines, TLC observations, reagent-table rows, yield, or column
details. Preserve uncertain text with [?] instead of inventing it. Keep the original order and
units.
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
        if not _needs_transcription_pass(draft):
            return draft, raw_response, content

        try:
            transcription_response = self.client.recognize(images, OCR_TRANSCRIPTION_PROMPT)
            transcription_content = self.client.extract_content(transcription_response)
        except OCRClientError as error:
            draft = _append_warning(
                draft,
                f"逐行转录补充请求失败，保留首轮 OCR 草稿：{error}",
            )
            return draft, raw_response, content
        try:
            transcription = parse_ocr_content(transcription_content, page_count=len(images))
        except OCRServiceError as error:
            transcription = parse_ocr_content(
                json.dumps({"raw_text": _strip_markdown_fence(transcription_content)}),
                page_count=len(images),
            )
            draft = _append_warning(
                draft,
                f"逐行转录返回了非标准 JSON，已按原文保留：{error}",
            )

        merged = _merge_transcription(draft, transcription)
        return (
            merged,
            {"structured": raw_response, "transcription": transcription_response},
            content + "\n\n" + transcription_content,
        )


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




def _strip_markdown_fence(content: str) -> str:
    stripped = content.strip()
    stripped = re.sub(r"^```(?:json|markdown)?\s*", "", stripped, flags=re.I)
    return re.sub(r"\s*```$", "", stripped).strip()


def _needs_transcription_pass(draft: OCRRecordDraft) -> bool:
    """Use a focused second pass when the structured pass omitted visible text."""

    return not draft.raw_text or not draft.workup.value or not draft.purification.value


def _merge_transcription(primary: OCRRecordDraft, transcription: OCRRecordDraft) -> OCRRecordDraft:
    """Merge full-page transcription into the role-aware first-pass draft."""

    payload = primary.model_dump(mode="json")
    if transcription.raw_text:
        payload["raw_text"] = transcription.raw_text
    for name in (
        "procedure",
        "workup",
        "purification",
        "temperature",
        "time",
        "solvent",
        "yield_mass",
        "yield_percent",
        "appearance",
    ):
        first = getattr(primary, name)
        second = getattr(transcription, name)
        generic = (
            name == "workup"
            and first.value
            and _is_generic_workup(str(first.value))
        ) or (
            name == "purification"
            and first.value
            and _is_generic_purification(str(first.value))
        )
        if (not first.value or generic) and second.value:
            payload[name] = second.model_dump(mode="json")
    if not primary.starting_materials and transcription.starting_materials:
        payload["starting_materials"] = [
            item.model_dump(mode="json") for item in transcription.starting_materials
        ]
    if not primary.reagents and transcription.reagents:
        payload["reagents"] = [item.model_dump(mode="json") for item in transcription.reagents]
    payload["warnings"] = _unique_strings(primary.warnings + transcription.warnings)
    payload["unmapped_text"] = _unique_strings(primary.unmapped_text + transcription.unmapped_text)
    return OCRRecordDraft.model_validate(payload)


def _append_warning(draft: OCRRecordDraft, warning: str) -> OCRRecordDraft:
    payload = draft.model_dump(mode="json")
    payload["warnings"] = _unique_strings([*draft.warnings, warning])
    return OCRRecordDraft.model_validate(payload)


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))




__all__ = [
    "OCRService",
    "OCRServiceError",
    "OCR_PROMPT",
    "OCR_TRANSCRIPTION_PROMPT",
    "parse_ocr_content",
]
