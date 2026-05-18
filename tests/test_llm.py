"""Phase 9 OpenAI SDK LLM helper tests.

These tests intentionally use fake clients or dry-run mode. They must not require network access or
an OpenAI API key.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from typer.testing import CliRunner

from chem_workflow.cli import app
from chem_workflow.llm import (
    AssignmentSummaryDraft,
    ExperimentRecordDraft,
    LLMWarning,
    OpenAIResponsesClient,
    OpenAISettings,
    draft_experiment_record,
    find_unsupported_characterization_claims,
    postprocess_assignment_summary_draft,
    summarize_assignment,
)
from chem_workflow.llm_models import LLMInputError, load_dotenv_if_present, resolve_api_key
from chem_workflow.records import load_reaction_record

FIXTURES = Path(__file__).resolve().parents[1] / "examples"
RECORD_FIXTURE = FIXTURES / "raw" / "experiment_record_example.yaml"
ASSIGNMENT_FIXTURE = FIXTURES / "processed" / "assignment_draft.md"


class FakeLLMClient:
    """Fake structured-output client that records the call and returns schema instances."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def parse_structured(
        self,
        *,
        settings: OpenAISettings,
        instructions: str,
        input_text: str,
        output_model: type[BaseModel],
        metadata: dict[str, str],
    ) -> tuple[BaseModel, str]:
        self.calls.append(
            {
                "settings": settings,
                "instructions": instructions,
                "input_text": input_text,
                "output_model": output_model,
                "metadata": metadata,
            }
        )
        if output_model is ExperimentRecordDraft:
            return (
                ExperimentRecordDraft(
                    title="Compound C001: ethyl benzoate",
                    markdown="# Compound C001\n\nDraft text.",
                    warnings=[],
                    source_fields_used=["compound_id", "characterization.h1_nmr"],
                ),
                "req_fake_record",
            )
        if output_model is AssignmentSummaryDraft:
            return (
                AssignmentSummaryDraft(
                    summary_markdown="Candidate-only assignment review summary.",
                    unresolved_items=["Review aromatic region manually."],
                    review_checklist=["Check integrations against expected proton count."],
                    warnings=[LLMWarning(code="manual_review_required", message="Review needed.")],
                ),
                "req_fake_assignment",
            )
        raise AssertionError(f"Unexpected output model: {output_model}")


def test_openai_settings_reads_model_and_base_url(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("CHEMWF_OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example/v1")

    settings = OpenAISettings.from_env()

    assert settings.model == "gpt-test"
    assert settings.base_url == "https://proxy.example/v1"


def test_openai_settings_cli_overrides_env_base_url(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example/v1")

    settings = OpenAISettings.from_env(model="gpt-cli", base_url="https://cli.example/v1")

    assert settings.model == "gpt-cli"
    assert settings.base_url == "https://cli.example/v1"


def test_openai_settings_reads_api_mode(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("CHEMWF_OPENAI_API_MODE", "chat-completions")

    settings = OpenAISettings.from_env()

    assert settings.api_mode == "chat-completions"


def test_openai_settings_supports_deepseek_defaults(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.setenv("CHEMWF_OPENAI_REASONING_EFFORT", "high")
    monkeypatch.setenv("CHEMWF_OPENAI_ENABLE_THINKING", "true")

    settings = OpenAISettings.from_env(base_url="https://api.deepseek.com")

    assert settings.api_key_env == "DEEPSEEK_API_KEY"
    assert settings.reasoning_effort == "high"
    assert settings.enable_thinking is True
    assert resolve_api_key(settings) == "sk-deepseek"


def test_openai_settings_rejects_endpoint_base_url() -> None:
    try:
        OpenAISettings.from_env(base_url="https://proxy.example/v1/chat/completions")
    except LLMInputError as e:
        assert "API 根路径" in str(e)
    else:
        raise AssertionError("Expected LLMInputError")


def test_dotenv_loader_reads_key_model_and_base_url(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("CHEMWF_OPENAI_MODEL", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=sk-test-from-dotenv",
                "OPENAI_BASE_URL=https://dotenv.example/v1",
                "CHEMWF_OPENAI_MODEL=gpt-dotenv",
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_dotenv_if_present(env_path)
    settings = OpenAISettings.from_env()

    assert loaded == env_path
    assert settings.model == "gpt-dotenv"
    assert settings.base_url == "https://dotenv.example/v1"
    assert os.environ["OPENAI_API_KEY"] == "sk-test-from-dotenv"


def test_dotenv_loader_does_not_override_existing_env(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("OPENAI_API_KEY", "sk-existing")
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=sk-from-file\n", encoding="utf-8")

    load_dotenv_if_present(env_path)

    assert os.environ["OPENAI_API_KEY"] == "sk-existing"


def test_draft_experiment_record_uses_fake_client() -> None:
    record = load_reaction_record(RECORD_FIXTURE)
    fake = FakeLLMClient()
    settings = OpenAISettings(model="gpt-test", base_url="https://proxy.example/v1")

    result = draft_experiment_record(record, settings=settings, client=fake)

    assert result.output.status == "draft"
    assert result.output.title == "Compound C001: ethyl benzoate"
    assert result.metadata.request_id == "req_fake_record"
    assert fake.calls[0]["settings"].base_url == "https://proxy.example/v1"
    assert fake.calls[0]["metadata"]["task"] == "experiment_record_en"
    assert "baseline_markdown" in fake.calls[0]["input_text"]


def test_summarize_assignment_uses_fake_client() -> None:
    fake = FakeLLMClient()
    settings = OpenAISettings(model="gpt-test")
    markdown = ASSIGNMENT_FIXTURE.read_text(encoding="utf-8")

    result = summarize_assignment(markdown, settings=settings, client=fake)

    assert result.output.status == "draft"
    assert result.output.unresolved_items
    assert result.metadata.request_id == "req_fake_assignment"
    assert fake.calls[0]["metadata"]["task"] == "assignment_summary"


def test_chat_completions_mode_parses_fake_response() -> None:
    class FakeMessage:
        content = '{"status": "draft", "summary_markdown": "Candidate summary."}'

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        id = "chatcmpl_fake"
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):  # noqa: ANN001
            self.kwargs = kwargs
            return FakeResponse()

    class FakeChat:
        def __init__(self) -> None:
            self.completions = FakeCompletions()

    class FakeSDKClient:
        def __init__(self) -> None:
            self.chat = FakeChat()

    client = object.__new__(OpenAIResponsesClient)
    client._client = FakeSDKClient()  # noqa: SLF001
    settings = OpenAISettings(
        model="gpt-test",
        api_mode="chat-completions",
        reasoning_effort="high",
        enable_thinking=True,
    )

    parsed, request_id = client.parse_structured(
        settings=settings,
        instructions="system",
        input_text="input",
        output_model=AssignmentSummaryDraft,
        metadata={"task": "assignment_summary"},
    )

    assert parsed.status == "draft"
    assert request_id == "chatcmpl_fake"
    kwargs = client._client.chat.completions.kwargs  # noqa: SLF001
    assert kwargs["stream"] is False
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


def test_find_unsupported_characterization_claims_flags_new_numbers() -> None:
    source = "1H NMR (400 MHz, CDCl3) δ 7.26 (s, 1H)."
    output = "1H NMR (400 MHz, CDCl3) δ 999.9 (s, 1H)."

    unsupported = find_unsupported_characterization_claims(output, source)

    assert unsupported == [output]


def test_assignment_postprocess_warns_on_overconfident_language() -> None:
    draft = AssignmentSummaryDraft(
        summary_markdown="This is a confirmed assignment for all aromatic peaks.",
        unresolved_items=[],
        review_checklist=[],
        warnings=[],
    )

    checked = postprocess_assignment_summary_draft(draft)

    assert any(warning.code == "overconfident_assignment_language" for warning in checked.warnings)


def test_cli_llm_draft_record_dry_run_does_not_need_api_key(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = CliRunner()

    result = runner.invoke(app, ["llm", "draft-record", str(RECORD_FIXTURE), "--dry-run-prompt"])

    assert result.exit_code == 0
    assert "## Instructions" in result.output
    assert "experiment_record_en" in result.output
    assert "baseline_markdown" in result.output


def test_cli_llm_summarize_assignment_dry_run_writes_file(
    tmp_path: Path,
    monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = CliRunner()
    out = tmp_path / "assignment_prompt.md"

    result = runner.invoke(
        app,
        [
            "llm",
            "summarize-assignment",
            str(ASSIGNMENT_FIXTURE),
            "--dry-run-prompt",
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0
    assert result.output == f"已写入 {out}\n"
    assert "assignment_summary" in out.read_text(encoding="utf-8")


def test_cli_llm_draft_record_without_api_key_is_clear(
    tmp_path: Path,
    monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("CHEMWF_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("CHEMWF_OPENAI_API_KEY_ENV", raising=False)
    monkeypatch.delenv("CHEMWF_ENV_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["llm", "draft-record", str(RECORD_FIXTURE)])

    assert result.exit_code == 1
    assert "OPENAI_API_KEY" in result.output
