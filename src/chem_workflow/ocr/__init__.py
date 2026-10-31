"""Local GLM-OCR integration for experiment-record drafts."""

from chem_workflow.ocr.client import GLMOCRClient, OCRClientError, OCRImage, infer_mime_type
from chem_workflow.ocr.models import OCRField, OCRMaterial, OCRRecordDraft, OCRServiceStatus
from chem_workflow.ocr.runtime import OCRRuntimeError, OCRRuntimeManager
from chem_workflow.ocr.service import (
    OCR_PROMPT,
    OCR_TRANSCRIPTION_PROMPT,
    OCRService,
    OCRServiceError,
    parse_ocr_content,
)

__all__ = [
    "GLMOCRClient",
    "OCRClientError",
    "OCRField",
    "OCRImage",
    "OCRMaterial",
    "OCRRecordDraft",
    "OCRRuntimeError",
    "OCRRuntimeManager",
    "OCRService",
    "OCRServiceError",
    "OCR_PROMPT",
    "OCR_TRANSCRIPTION_PROMPT",
    "OCRServiceStatus",
    "infer_mime_type",
    "parse_ocr_content",
]
