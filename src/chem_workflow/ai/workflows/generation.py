"""Agent SDK backed helpers for draft-only chemistry writing tasks.

The selected Agents SDK owns model calls, structured output parsing, and tracing. Unit tests patch
the SDK runner boundary and must not require a real API key or network access.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents import RunConfig, Runner
from pydantic import BaseModel

from chem_workflow.ai.agents.generation import build_generation_agent
from chem_workflow.ai.schemas import (
    AssignmentSummaryDraft,
    ExperimentRecordDraft,
    LLMInputError,
    LLMRunMetadata,
    LLMServiceError,
    LLMWarning,
    OpenAISettings,
    OutputT,
    PromptTemplate,
    StructuredLLMResult,
)
from chem_workflow.core.resources import resource_path
from chem_workflow.records import ReactionRecord, render_experiment_record

PROMPTS_DIR = resource_path("prompts", "assignment_summary.txt").parent

_PROMPT_VERSION_RE = re.compile(r"^Prompt-Version:\s*(?P<version>\S+)\s*$", re.MULTILINE)
_SPECTROSCOPY_LINE_RE = re.compile(
    r"\b(?:1H|13C|19F|31P)?\s*(?:NMR|HRMS|MS|IR|UV(?:-vis)?)\b.*",
    flags=re.IGNORECASE,
)
_NUMBER_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")
_OVERCONFIDENT_ASSIGNMENT_RE = re.compile(
    r"\b(?:confirmed|proven|proved|definitive|unambiguous)\s+assignment\b",
    flags=re.IGNORECASE,
)


def load_prompt(name: str) -> PromptTemplate:
    """Load a prompt template by filename stem from `prompts/`."""
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise LLMInputError(f"找不到 prompt 模板：{path}")
    text = path.read_text(encoding="utf-8")
    match = _PROMPT_VERSION_RE.search(text)
    if match is None:
        raise LLMInputError(f"prompt 模板缺少 Prompt-Version：{path}")
    return PromptTemplate(name=name, version=match.group("version"), text=text, path=path)


def build_experiment_record_input(
    record: ReactionRecord,
    *,
    style: str = "supporting-information",
) -> dict[str, Any]:
    """Build the JSON payload for experiment-record drafting."""
    baseline_markdown = render_experiment_record(record, language="en")
    return {
        "task": "experiment_record_en",
        "style": style,
        "record": record.model_dump(mode="json", by_alias=True),
        "baseline_markdown": baseline_markdown,
        "constraints": {
            "status": "draft",
            "do_not_invent_characterization": True,
            "preserve_numbers_and_units": True,
        },
    }


def build_assignment_summary_input(assignment_markdown: str) -> dict[str, Any]:
    """Build the JSON payload for assignment-summary drafting."""
    if not assignment_markdown.strip():
        raise LLMInputError("assignment draft 为空，无法生成 LLM summary。")
    return {
        "task": "assignment_summary",
        "assignment_draft_markdown": assignment_markdown,
        "constraints": {
            "status": "draft",
            "candidate_only": True,
            "manual_confirmation_required": True,
        },
    }


def render_dry_run_prompt(instructions: str, input_payload: dict[str, Any]) -> str:
    """Render the exact instructions and input JSON without calling the SDK."""
    input_text = _json_dumps(input_payload)
    return f"## Instructions\n\n{instructions}\n\n## Input JSON\n\n```json\n{input_text}\n```\n"


def draft_experiment_record(
    record: ReactionRecord,
    *,
    settings: OpenAISettings,
    style: str = "supporting-information",
) -> StructuredLLMResult[ExperimentRecordDraft]:
    """Generate a draft experiment record with structured output."""
    prompt = load_prompt("experiment_record_en")
    input_payload = build_experiment_record_input(record, style=style)
    result = _run_agent(
        task="experiment_record_en",
        settings=settings,
        prompt=prompt,
        input_payload=input_payload,
        output_model=ExperimentRecordDraft,
    )
    output = postprocess_experiment_record_draft(result.output, input_payload)
    return StructuredLLMResult(
        output=output,
        metadata=result.metadata,
        input_payload=result.input_payload,
        prompt=result.prompt,
    )


def summarize_assignment(
    assignment_markdown: str,
    *,
    settings: OpenAISettings,
) -> StructuredLLMResult[AssignmentSummaryDraft]:
    """Generate a draft summary for a rule-based assignment draft."""
    prompt = load_prompt("assignment_summary")
    input_payload = build_assignment_summary_input(assignment_markdown)
    result = _run_agent(
        task="assignment_summary",
        settings=settings,
        prompt=prompt,
        input_payload=input_payload,
        output_model=AssignmentSummaryDraft,
    )
    output = postprocess_assignment_summary_draft(result.output)
    return StructuredLLMResult(
        output=output,
        metadata=result.metadata,
        input_payload=result.input_payload,
        prompt=result.prompt,
    )


def build_warning_summary_input(assignment_markdown: str) -> dict[str, Any]:
    """Build the JSON payload for summarizing assignment warnings."""
    if not assignment_markdown.strip():
        raise LLMInputError("assignment draft 为空，无法生成 warning summary。")
    return {
        "task": "warning_summary",
        "assignment_draft_markdown": assignment_markdown,
        "constraints": {
            "status": "draft",
            "do_not_resolve_automatically": True,
            "manual_confirmation_required": True,
        },
    }


def build_polish_record_input(
    record_markdown: str,
    *,
    language: str = "en",
    style: str = "supporting-information",
) -> dict[str, Any]:
    """Build the JSON payload for polishing an existing experiment record."""
    if not record_markdown.strip():
        raise LLMInputError("实验记录为空，无法进行 LLM 润色。")
    return {
        "task": "polish_record",
        "language": language,
        "style": style,
        "record_markdown": record_markdown,
        "constraints": {
            "status": "draft",
            "preserve_numbers_and_units": True,
            "do_not_invent_characterization": True,
        },
    }


def summarize_warnings(
    assignment_markdown: str,
    *,
    settings: OpenAISettings,
) -> StructuredLLMResult[AssignmentSummaryDraft]:
    """Summarize warnings in a rule-based assignment draft for human review."""
    prompt = load_prompt("warning_summary")
    input_payload = build_warning_summary_input(assignment_markdown)
    result = _run_agent(
        task="warning_summary",
        settings=settings,
        prompt=prompt,
        input_payload=input_payload,
        output_model=AssignmentSummaryDraft,
    )
    output = postprocess_assignment_summary_draft(result.output)
    return StructuredLLMResult(
        output=output,
        metadata=result.metadata,
        input_payload=result.input_payload,
        prompt=result.prompt,
    )


def polish_record(
    record_markdown: str,
    *,
    settings: OpenAISettings,
    language: str = "en",
    style: str = "supporting-information",
) -> StructuredLLMResult[ExperimentRecordDraft]:
    """Polish an existing experiment record into a draft supporting-information style."""
    prompt = load_prompt("polish_record")
    input_payload = build_polish_record_input(record_markdown, language=language, style=style)
    result = _run_agent(
        task="polish_record",
        settings=settings,
        prompt=prompt,
        input_payload=input_payload,
        output_model=ExperimentRecordDraft,
    )
    output = postprocess_experiment_record_draft(result.output, input_payload)
    return StructuredLLMResult(
        output=output,
        metadata=result.metadata,
        input_payload=result.input_payload,
        prompt=result.prompt,
    )


def postprocess_experiment_record_draft(
    draft: ExperimentRecordDraft,
    source_payload: dict[str, Any],
) -> ExperimentRecordDraft:
    """Add conservative warnings for spectroscopy claims that are not in the input."""
    source_text = _json_dumps(source_payload)
    unsupported = find_unsupported_characterization_claims(draft.markdown, source_text)
    warnings = list(draft.warnings)
    if unsupported:
        warnings.append(
            LLMWarning(
                code="unsupported_characterization_claim",
                message=(
                    "LLM draft may contain characterization numbers not found in the structured "
                    "input. Review unsupported_claims before using the Markdown."
                ),
                severity="risk",
            )
        )
    return draft.model_copy(
        update={
            "unsupported_claims": sorted(set(draft.unsupported_claims) | set(unsupported)),
            "warnings": warnings,
        }
    )


def postprocess_assignment_summary_draft(
    draft: AssignmentSummaryDraft,
) -> AssignmentSummaryDraft:
    """Warn if the summary accidentally overclaims assignment certainty."""
    warnings = list(draft.warnings)
    if _OVERCONFIDENT_ASSIGNMENT_RE.search(draft.summary_markdown):
        warnings.append(
            LLMWarning(
                code="overconfident_assignment_language",
                message=(
                    "Summary contains language that may overstate assignment certainty. "
                    "Keep assignment text candidate-only until manually confirmed."
                ),
                severity="risk",
            )
        )
    return draft.model_copy(update={"warnings": warnings})


def find_unsupported_characterization_claims(output_text: str, source_text: str) -> list[str]:
    """Find spectroscopy lines containing numeric tokens absent from the source text."""
    source_numbers = set(_NUMBER_TOKEN_RE.findall(source_text))
    unsupported: list[str] = []
    for line in output_text.splitlines():
        if not _SPECTROSCOPY_LINE_RE.search(line):
            continue
        line_numbers = set(_NUMBER_TOKEN_RE.findall(line))
        if line_numbers - source_numbers:
            unsupported.append(line.strip())
    return unsupported


def save_llm_run(result: StructuredLLMResult[BaseModel], runs_dir: str | Path) -> Path:
    """Persist prompt, input, output, and metadata for traceability."""
    root = Path(runs_dir)
    timestamp = result.metadata.created_at.strftime("%Y%m%d_%H%M%S")
    run_dir = root / f"{timestamp}_{result.metadata.task}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "input.json").write_text(
        _json_dumps(result.input_payload) + "\n",
        encoding="utf-8",
    )
    (run_dir / "output.json").write_text(
        result.output.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "metadata.json").write_text(
        result.metadata.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "prompt.txt").write_text(result.prompt.text, encoding="utf-8")
    return run_dir


def _run_agent(
    *,
    task: str,
    settings: OpenAISettings,
    prompt: PromptTemplate,
    input_payload: dict[str, Any],
    output_model: type[OutputT],
) -> StructuredLLMResult[OutputT]:
    input_text = _json_dumps(input_payload)
    run_metadata = LLMRunMetadata(
        task=task,
        model=settings.model,
        prompt_version=prompt.version,
        created_at=datetime.now(UTC),
        input_hash=_input_hash(input_payload),
    )
    trace_metadata = {
        "task": task,
        "prompt_version": prompt.version,
        "input_hash": run_metadata.input_hash,
    }
    agent = build_generation_agent(
        task=task,
        settings=settings,
        prompt=prompt,
        output_type=output_model,
    )
    try:
        sdk_result = Runner.run_sync(
            agent,
            input_text,
            max_turns=1,
            run_config=RunConfig(
                workflow_name=task,
                trace_metadata=trace_metadata,
                tracing_disabled=settings.base_url is not None,
            ),
        )
        raw_output = sdk_result.final_output
        output = (
            raw_output
            if isinstance(raw_output, output_model)
            else output_model.model_validate(raw_output)
        )
    except Exception as e:  # noqa: BLE001 - Agents SDK wraps provider-specific exceptions.
        raise LLMServiceError(f"Agent SDK 执行失败：{e}") from e
    return StructuredLLMResult(
        output=output,
        metadata=run_metadata.model_copy(update={"request_id": sdk_result.last_response_id}),
        input_payload=input_payload,
        prompt=prompt,
    )


def _input_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)



