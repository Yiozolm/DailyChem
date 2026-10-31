"""Local GLM-OCR integration for experiment-record drafts."""

from chem_workflow.ocr.client import GLMOCRClient, OCRClientError, OCRImage, infer_mime_type
from chem_workflow.ocr.models import (
    OCRField,
    OCRMaterial,
    OCRRecordDraft,
    OCRServiceStatus,
    OCRTableRow,
)
from chem_workflow.ocr.runtime import OCRRuntimeError, OCRRuntimeManager
from chem_workflow.ocr.service import (
    OCR_TEXT_PROMPT,
    OCRService,
    OCRServiceError,
    parse_ocr_content,
)
from chem_workflow.ocr.stoichiometry import check_material_table, check_yield
from chem_workflow.ocr.transcript import (
    clean_transcript,
    draft_from_transcript,
    parse_material_table,
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
    "OCR_TEXT_PROMPT",
    "OCRServiceStatus",
    "OCRTableRow",
    "check_material_table",
    "check_yield",
    "clean_transcript",
    "draft_from_transcript",
    "infer_mime_type",
    "parse_material_table",
    "parse_ocr_content",
]
