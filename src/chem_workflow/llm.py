"""Compatibility exports for Agent SDK chemistry generation workflows."""

from chem_workflow.ai.schemas import (
    AssignmentSummaryDraft,
    ExperimentRecordDraft,
    LLMWarning,
    OpenAISettings,
)
from chem_workflow.ai.sdk.bootstrap import ensure_openai_api_key
from chem_workflow.ai.workflows import (
    build_assignment_summary_input,
    build_experiment_record_input,
    build_polish_record_input,
    build_warning_summary_input,
    draft_experiment_record,
    find_unsupported_characterization_claims,
    load_prompt,
    polish_record,
    postprocess_assignment_summary_draft,
    postprocess_experiment_record_draft,
    render_dry_run_prompt,
    save_llm_run,
    summarize_assignment,
    summarize_warnings,
)

__all__ = [
    "AssignmentSummaryDraft",
    "ExperimentRecordDraft",
    "LLMWarning",
    "OpenAISettings",
    "build_assignment_summary_input",
    "build_experiment_record_input",
    "build_polish_record_input",
    "build_warning_summary_input",
    "draft_experiment_record",
    "ensure_openai_api_key",
    "find_unsupported_characterization_claims",
    "load_prompt",
    "polish_record",
    "postprocess_assignment_summary_draft",
    "postprocess_experiment_record_draft",
    "render_dry_run_prompt",
    "save_llm_run",
    "summarize_assignment",
    "summarize_warnings",
]
