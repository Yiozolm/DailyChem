"""Local GLM-OCR transcription service and JSON draft parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from chem_workflow.ocr.client import GLMOCRClient, OCRClientError, OCRImage
from chem_workflow.ocr.models import OCRRecordDraft
from chem_workflow.ocr.normalization import _normalize_payload
from chem_workflow.ocr.transcript import draft_from_transcript

# GLM-OCR's native task prompt. Asking this small model to fill a large JSON schema caused
# wrong field mapping and, on some pages, a repetition loop until max_tokens; mapping is done
# in code instead (see ``transcript.py``).
OCR_TEXT_PROMPT = "Text Recognition:"


class OCRServiceError(RuntimeError):
    """Raised when the OCR response cannot be converted into a safe draft."""


class OCRService:
    """Transcribe each photo with local GLM-OCR and build a review-required draft."""

    def __init__(self, client: GLMOCRClient) -> None:
        self.client = client

    def recognize(self, images: list[OCRImage]) -> tuple[OCRRecordDraft, dict[str, object], str]:
        """Return structured draft, raw per-page responses, and the joined transcript."""
        if not images:
            raise OCRServiceError("至少需要一张图片。")
        pages: list[dict[str, object]] = []
        texts: list[str] = []
        warnings: list[str] = []
        for index, image in enumerate(images, start=1):
            try:
                response = self.client.recognize([image], OCR_TEXT_PROMPT)
                text = self.client.extract_content(response)
            except OCRClientError as error:
                warnings.append(f"第 {index} 张照片（{image.name}）识别失败：{error}")
                pages.append({"image": image.name, "error": str(error)})
                continue
            if _finish_reason(response) == "length":
                warnings.append(
                    f"第 {index} 张照片的识别输出达到长度上限，可能被截断，请对照照片核对。"
                )
            pages.append({"image": image.name, "response": response})
            texts.append(text)
        if not texts:
            raise OCRServiceError("所有照片都识别失败：" + "；".join(warnings))
        content = "\n\n".join(texts)
        draft = draft_from_transcript(content, page_count=len(images), warnings=warnings)
        return draft, {"pages": pages}, content


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


def _finish_reason(response: dict[str, object]) -> object:
    choices = response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return choices[0].get("finish_reason")
    return None


__all__ = [
    "OCRService",
    "OCRServiceError",
    "OCR_TEXT_PROMPT",
    "parse_ocr_content",
]
