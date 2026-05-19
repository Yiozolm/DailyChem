"""OpenAI SDK backed LLM helpers for draft-only chemistry writing tasks.

This module deliberately keeps OpenAI access behind a small, mockable wrapper. Unit tests should
use fake clients and must not require a real API key or network access.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from chem_workflow.llm_models import (
    AssignmentSummaryDraft,
    ExperimentRecordDraft,
    LLMClientProtocol,
    LLMInputError,
    LLMRunMetadata,
    LLMServiceError,
    LLMWarning,
    OpenAISettings,
    OutputT,
    PromptTemplate,
    StructuredLLMResult,
    load_dotenv_if_present,
    resolve_api_key,
    validate_openai_base_url,
)
from chem_workflow.records import ReactionRecord, render_experiment_record

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

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


class OpenAIResponsesClient:
    """OpenAI Responses API adapter using structured outputs."""

    def __init__(self, settings: OpenAISettings) -> None:
        api_key = ensure_openai_api_key(settings)
        try:
            from openai import OpenAI
        except ImportError as e:
            raise LLMInputError(
                "未安装 openai Python SDK。请先运行 `uv sync` 或安装项目依赖。"
            ) from e

        validate_openai_base_url(settings.base_url)
        kwargs: dict[str, object] = {"api_key": api_key, "timeout": settings.timeout_seconds}
        if settings.base_url:
            kwargs["base_url"] = settings.base_url
        self._client = OpenAI(**kwargs)

    def parse_structured(
        self,
        *,
        settings: OpenAISettings,
        instructions: str,
        input_text: str,
        output_model: type[OutputT],
        metadata: dict[str, str],
    ) -> tuple[OutputT, str | None]:
        """Call the configured OpenAI-compatible structured-output endpoint."""
        if settings.api_mode == "chat-completions":
            return self._parse_chat_completions(
                settings=settings,
                instructions=instructions,
                input_text=input_text,
                output_model=output_model,
                metadata=metadata,
            )
        return self._parse_responses(
            settings=settings,
            instructions=instructions,
            input_text=input_text,
            output_model=output_model,
            metadata=metadata,
        )

    def _parse_responses(
        self,
        *,
        settings: OpenAISettings,
        instructions: str,
        input_text: str,
        output_model: type[OutputT],
        metadata: dict[str, str],
    ) -> tuple[OutputT, str | None]:
        """Call `responses.parse` and return the parsed structured output."""
        try:
            response = self._client.responses.parse(
                model=settings.model,
                instructions=instructions,
                input=input_text,
                text_format=output_model,
                metadata=metadata,
                max_output_tokens=settings.max_output_tokens,
                store=settings.store,
            )
        except Exception as e:  # noqa: BLE001 - SDK exception types may vary across versions.
            raise LLMServiceError(_format_openai_error(e, settings)) from e

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise LLMServiceError("OpenAI 响应没有可用的 structured output。")
        request_id = getattr(response, "_request_id", None)
        if request_id is None:
            request_id = getattr(response, "id", None)
        return parsed, request_id

    def _parse_chat_completions(
        self,
        *,
        settings: OpenAISettings,
        instructions: str,
        input_text: str,
        output_model: type[OutputT],
        metadata: dict[str, str],
    ) -> tuple[OutputT, str | None]:
        """Call plain `chat.completions.create` for OpenAI-compatible gateways."""
        try:
            response = self._client.chat.completions.create(
                model=settings.model,
                messages=[
                    {
                        "role": "system",
                        "content": _chat_json_system_prompt(instructions, output_model),
                    },
                    {"role": "user", "content": input_text},
                ],
                stream=False,
                max_tokens=settings.max_output_tokens,
                **_chat_extra_kwargs(settings),
            )
        except Exception as e:  # noqa: BLE001 - SDK exception types may vary across versions.
            raise LLMServiceError(_format_openai_error(e, settings)) from e

        _ = metadata  # Local run metadata is still saved by `save_llm_run`.
        content = response.choices[0].message.content
        parsed = _parse_chat_json_content(content, output_model)
        request_id = getattr(response, "_request_id", None)
        if request_id is None:
            request_id = getattr(response, "id", None)
        return parsed, request_id


def ensure_openai_api_key(settings: OpenAISettings | None = None) -> str:
    """Raise a user-facing error when `OPENAI_API_KEY` is not configured."""
    load_dotenv_if_present()
    active_settings = settings or OpenAISettings.from_env()
    api_key = resolve_api_key(active_settings)
    if not api_key:
        key_hint = active_settings.api_key_env or "OPENAI_API_KEY"
        raise LLMInputError(
            f"未检测到 {key_hint}。请先设置环境变量，例如："
            f" export {key_hint}='your-key-here'；也可以在项目根目录 `.env` 中配置。"
        )
    return api_key


def _chat_json_system_prompt(instructions: str, output_model: type[BaseModel]) -> str:
    schema = output_model.model_json_schema()
    return (
        f"{instructions}\n\n"
        "You must return exactly one valid JSON object and no Markdown fences.\n"
        "The JSON object must conform to this JSON Schema:\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
    )


def _chat_extra_kwargs(settings: OpenAISettings) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    if settings.reasoning_effort:
        kwargs["reasoning_effort"] = settings.reasoning_effort
    if settings.enable_thinking:
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    return kwargs


def _parse_chat_json_content(content: str | None, output_model: type[OutputT]) -> OutputT:
    if not content:
        raise LLMServiceError("Chat Completions 响应为空，无法解析 JSON structured output。")
    json_text = _extract_json_object(content)
    try:
        return output_model.model_validate_json(json_text)
    except Exception as e:
        raise LLMServiceError(
            "Chat Completions 响应不是符合 schema 的 JSON。"
            "如果 provider 支持 Responses API，可改用 `--api-mode responses`；"
            "否则请保留 `--api-mode chat-completions` 并检查模型是否遵循 JSON 输出。"
        ) from e


def _extract_json_object(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


def _format_openai_error(error: Exception, settings: OpenAISettings) -> str:
    """Add actionable context to SDK errors without exposing secrets."""
    status_code = getattr(error, "status_code", None)
    message = str(error)
    if status_code == 404:
        return (
            "OpenAI API 调用失败：404 Not Found。常见原因："
            "\n1. 当前 `api_mode=responses` 会调用 `/responses`，但你的 OpenAI-compatible "
            "服务可能只支持 `/chat/completions`；请尝试 "
            "`--api-mode chat-completions` 或设置 "
            "`CHEMWF_OPENAI_API_MODE=chat-completions`。"
            "\n2. `base_url` 必须是 API 根路径，例如 `https://.../v1`，不要填到 "
            "`/responses` 或 `/chat/completions`。"
            "\n3. 当前 provider 可能不支持模型 "
            f"`{settings.model}`；请用 `--model` 换成该 provider 实际支持的模型。"
            f"\n当前配置：api_mode={settings.api_mode}, base_url="
            f"{settings.base_url or '<SDK default>'}, model={settings.model}。"
            f"\n原始错误：{message}"
        )
    return f"OpenAI API 调用失败：{message}"


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
    client: LLMClientProtocol | None = None,
) -> StructuredLLMResult[ExperimentRecordDraft]:
    """Generate a draft experiment record with structured output."""
    prompt = load_prompt("experiment_record_en")
    input_payload = build_experiment_record_input(record, style=style)
    result = _parse_with_client(
        task="experiment_record_en",
        settings=settings,
        prompt=prompt,
        input_payload=input_payload,
        output_model=ExperimentRecordDraft,
        client=client,
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
    client: LLMClientProtocol | None = None,
) -> StructuredLLMResult[AssignmentSummaryDraft]:
    """Generate a draft summary for a rule-based assignment draft."""
    prompt = load_prompt("assignment_summary")
    input_payload = build_assignment_summary_input(assignment_markdown)
    result = _parse_with_client(
        task="assignment_summary",
        settings=settings,
        prompt=prompt,
        input_payload=input_payload,
        output_model=AssignmentSummaryDraft,
        client=client,
    )
    output = postprocess_assignment_summary_draft(result.output)
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


def _parse_with_client(
    *,
    task: str,
    settings: OpenAISettings,
    prompt: PromptTemplate,
    input_payload: dict[str, Any],
    output_model: type[OutputT],
    client: LLMClientProtocol | None,
) -> StructuredLLMResult[OutputT]:
    input_text = _json_dumps(input_payload)
    run_metadata = LLMRunMetadata(
        task=task,
        model=settings.model,
        prompt_version=prompt.version,
        created_at=datetime.now(UTC),
        input_hash=_input_hash(input_payload),
    )
    active_client = client or OpenAIResponsesClient(settings)
    output, request_id = active_client.parse_structured(
        settings=settings,
        instructions=prompt.text,
        input_text=input_text,
        output_model=output_model,
        metadata={
            "task": task,
            "prompt_version": prompt.version,
            "input_hash": run_metadata.input_hash,
        },
    )
    return StructuredLLMResult(
        output=output,
        metadata=run_metadata.model_copy(update={"request_id": request_id}),
        input_payload=input_payload,
        prompt=prompt,
    )


def _input_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
