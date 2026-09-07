"""Agent SDK chemistry workflow tests.

These tests patch the SDK Runner boundary or use dry-run mode. They must not require network access.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from agents import OpenAIChatCompletionsModel
from typer.testing import CliRunner

from chem_workflow.ai.sdk.bootstrap import build_agent_model, build_model_settings
from chem_workflow.ai.workflows import generation
from chem_workflow.cli import app
from chem_workflow.llm import (
    AssignmentSummaryDraft,
    ExperimentRecordDraft,
    LLMWarning,
    OpenAISettings,
    build_polish_record_input,
    draft_experiment_record,
    find_unsupported_characterization_claims,
    polish_record,
    postprocess_assignment_summary_draft,
    summarize_assignment,
    summarize_warnings,
)
from chem_workflow.llm_models import LLMInputError, load_dotenv_if_present, resolve_api_key
from chem_workflow.records import load_reaction_record

FIXTURES = Path(__file__).resolve().parents[1] / "examples"
RECORD_FIXTURE = FIXTURES / "raw" / "experiment_record_example.yaml"
ASSIGNMENT_FIXTURE = FIXTURES / "processed" / "assignment_draft.md"
RECORD_MD_FIXTURE = FIXTURES / "processed" / "experiment_record.md"


@pytest.fixture
def fake_agent_runner(monkeypatch):  # noqa: ANN001
    """Capture SDK-native Agent/Runner calls without issuing network requests."""
    calls: list[dict[str, object]] = []
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def run_sync(agent, input_text, **kwargs):  # noqa: ANN001
        calls.append(
            {
                "agent": agent,
                "input_text": input_text,
                "run_config": kwargs["run_config"],
            }
        )
        if agent.output_type is ExperimentRecordDraft:
            output = ExperimentRecordDraft(
                title="Compound C001: ethyl benzoate",
                markdown="# Compound C001\n\nDraft text.",
                warnings=[],
                source_fields_used=["compound_id", "characterization.h1_nmr"],
            )
            response_id = "resp_fake_record"
        elif agent.output_type is AssignmentSummaryDraft:
            output = AssignmentSummaryDraft(
                summary_markdown="Candidate-only assignment review summary.",
                unresolved_items=["Review aromatic region manually."],
                review_checklist=["Check integrations against expected proton count."],
                warnings=[LLMWarning(code="manual_review_required", message="Review needed.")],
            )
            response_id = "resp_fake_assignment"
        else:
            raise AssertionError(f"Unexpected output model: {agent.output_type}")
        return SimpleNamespace(final_output=output, last_response_id=response_id)

    monkeypatch.setattr(generation.Runner, "run_sync", staticmethod(run_sync))
    return calls


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


def test_draft_experiment_record_uses_agent_runner(fake_agent_runner) -> None:  # noqa: ANN001
    record = load_reaction_record(RECORD_FIXTURE)
    settings = OpenAISettings(model="gpt-test", base_url="https://proxy.example/v1")

    result = draft_experiment_record(record, settings=settings)

    assert result.output.status == "draft"
    assert result.output.title == "Compound C001: ethyl benzoate"
    assert result.metadata.request_id == "resp_fake_record"
    assert fake_agent_runner[0]["agent"].name == "experiment_record_en"
    assert fake_agent_runner[0]["run_config"].trace_metadata["task"] == "experiment_record_en"
    assert "baseline_markdown" in fake_agent_runner[0]["input_text"]


def test_summarize_assignment_uses_agent_runner(fake_agent_runner) -> None:  # noqa: ANN001
    settings = OpenAISettings(model="gpt-test")
    markdown = ASSIGNMENT_FIXTURE.read_text(encoding="utf-8")

    result = summarize_assignment(markdown, settings=settings)

    assert result.output.status == "draft"
    assert result.output.unresolved_items
    assert result.metadata.request_id == "resp_fake_assignment"
    assert fake_agent_runner[0]["agent"].name == "assignment_summary"


def test_summarize_warnings_uses_agent_runner(fake_agent_runner) -> None:  # noqa: ANN001
    settings = OpenAISettings(model="gpt-test")
    markdown = ASSIGNMENT_FIXTURE.read_text(encoding="utf-8")

    result = summarize_warnings(markdown, settings=settings)

    assert result.output.status == "draft"
    assert result.metadata.request_id == "resp_fake_assignment"
    assert fake_agent_runner[0]["agent"].name == "warning_summary"
    assert "assignment_draft_markdown" in fake_agent_runner[0]["input_text"]


def test_polish_record_uses_agent_runner(fake_agent_runner) -> None:  # noqa: ANN001
    settings = OpenAISettings(model="gpt-test")
    markdown = RECORD_MD_FIXTURE.read_text(encoding="utf-8")

    result = polish_record(markdown, settings=settings, language="en")

    assert result.output.status == "draft"
    assert result.metadata.request_id == "resp_fake_record"
    assert fake_agent_runner[0]["agent"].name == "polish_record"
    assert "record_markdown" in fake_agent_runner[0]["input_text"]


def test_build_polish_record_input_rejects_empty() -> None:
    try:
        build_polish_record_input("   \n")
    except LLMInputError as e:
        assert "实验记录" in str(e)
    else:
        raise AssertionError("Expected LLMInputError")


def test_chat_completions_mode_uses_agents_sdk_model(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = OpenAISettings(
        model="gpt-test",
        api_mode="chat-completions",
        reasoning_effort="high",
        enable_thinking=True,
    )

    model = build_agent_model(settings)
    model_settings = build_model_settings(settings)

    assert isinstance(model, OpenAIChatCompletionsModel)
    assert model_settings.reasoning is not None
    assert model_settings.reasoning.effort == "high"
    assert model_settings.extra_body == {"thinking": {"type": "enabled"}}


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


def test_cli_llm_summarize_warnings_dry_run(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = CliRunner()

    result = runner.invoke(
        app, ["llm", "summarize-warnings", str(ASSIGNMENT_FIXTURE), "--dry-run-prompt"]
    )

    assert result.exit_code == 0
    assert "## Instructions" in result.output
    assert "warning_summary" in result.output


def test_cli_llm_polish_record_dry_run(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = CliRunner()

    result = runner.invoke(
        app, ["llm", "polish-record", str(RECORD_MD_FIXTURE), "--dry-run-prompt"]
    )

    assert result.exit_code == 0
    assert "## Instructions" in result.output
    assert "polish_record" in result.output
    assert "record_markdown" in result.output


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
