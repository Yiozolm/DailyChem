"""Typer commands for Phase 9 LLM helpers."""

from __future__ import annotations

from pathlib import Path

import typer

from chem_workflow.llm import (
    build_assignment_summary_input,
    build_experiment_record_input,
    draft_experiment_record,
    load_prompt,
    render_dry_run_prompt,
    save_llm_run,
    summarize_assignment,
)
from chem_workflow.llm_models import ApiMode, LLMInputError, LLMServiceError, OpenAISettings
from chem_workflow.records import RecordInputError, load_reaction_record

llm_app = typer.Typer(help="OpenAI SDK LLM 辅助命令；所有输出均为 draft", no_args_is_help=True)


@llm_app.command("draft-record")
def llm_draft_record(
    input_path: Path = typer.Argument(
        ...,
        help="实验记录结构化输入（.yaml / .yml / .json）",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    style: str = typer.Option(
        "supporting-information",
        "--style",
        help="LLM 草稿风格，例如 supporting-information",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="OpenAI model；默认读 CHEMWF_OPENAI_MODEL，否则 gpt-5.4-mini",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="OpenAI-compatible endpoint；默认读 OPENAI_BASE_URL / CHEMWF_OPENAI_BASE_URL",
    ),
    api_mode: ApiMode | None = typer.Option(
        None,
        "--api-mode",
        help="API endpoint 模式：responses 或 chat-completions",
    ),
    api_key_env: str | None = typer.Option(
        None,
        "--api-key-env",
        help="读取 API key 的环境变量名；DeepSeek 可用 DEEPSEEK_API_KEY",
    ),
    reasoning_effort: str | None = typer.Option(
        None,
        "--reasoning-effort",
        help="传给 chat.completions.create 的 reasoning_effort，例如 high",
    ),
    enable_thinking: bool | None = typer.Option(
        None,
        "--enable-thinking/--disable-thinking",
        help="为 DeepSeek 等 provider 传 extra_body thinking enabled",
    ),
    max_output_tokens: int = typer.Option(
        4000,
        "--max-output-tokens",
        help="OpenAI Responses API max_output_tokens",
    ),
    timeout_seconds: float = typer.Option(60.0, "--timeout", help="OpenAI SDK timeout 秒数"),
    store: bool = typer.Option(False, "--store/--no-store", help="是否允许 OpenAI 远端保存响应"),
    dry_run_prompt: bool = typer.Option(
        False,
        "--dry-run-prompt",
        help="只打印将发送给 LLM 的 prompt/input，不调用 OpenAI SDK",
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help="输出 JSON 或 dry-run prompt 到文件"),
    save_run: bool = typer.Option(
        False,
        "--save-run/--no-save-run",
        help="保存 input/output/metadata/prompt 到 runs-dir",
    ),
    runs_dir: Path = typer.Option(
        Path("llm_runs"),
        "--runs-dir",
        help="--save-run 的保存目录",
    ),
) -> None:
    """用 OpenAI SDK 从结构化记录生成英文实验记录 draft JSON。"""
    try:
        record = load_reaction_record(input_path)
        if dry_run_prompt:
            prompt = load_prompt("experiment_record_en")
            payload = build_experiment_record_input(record, style=style)
            _emit_text(render_dry_run_prompt(prompt.text, payload), out)
            return

        settings = _build_llm_settings(
            model=model,
            base_url=base_url,
            api_mode=api_mode,
            api_key_env=api_key_env,
            reasoning_effort=reasoning_effort,
            enable_thinking=enable_thinking,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
            store=store,
        )
        result = draft_experiment_record(record, settings=settings, style=style)
        if save_run:
            run_dir = save_llm_run(result, runs_dir)
            typer.echo(f"LLM run 已保存：{run_dir}", err=True)
        _emit_json(result.output.model_dump_json(indent=2) + "\n", out)
    except (RecordInputError, LLMInputError, LLMServiceError) as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e


@llm_app.command("summarize-assignment")
def llm_summarize_assignment(
    input_path: Path = typer.Argument(
        ...,
        help="rule-based assignment draft Markdown 或文本文件",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="OpenAI model；默认读 CHEMWF_OPENAI_MODEL，否则 gpt-5.4-mini",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="OpenAI-compatible endpoint；默认读 OPENAI_BASE_URL / CHEMWF_OPENAI_BASE_URL",
    ),
    api_mode: ApiMode | None = typer.Option(
        None,
        "--api-mode",
        help="API endpoint 模式：responses 或 chat-completions",
    ),
    api_key_env: str | None = typer.Option(
        None,
        "--api-key-env",
        help="读取 API key 的环境变量名；DeepSeek 可用 DEEPSEEK_API_KEY",
    ),
    reasoning_effort: str | None = typer.Option(
        None,
        "--reasoning-effort",
        help="传给 chat.completions.create 的 reasoning_effort，例如 high",
    ),
    enable_thinking: bool | None = typer.Option(
        None,
        "--enable-thinking/--disable-thinking",
        help="为 DeepSeek 等 provider 传 extra_body thinking enabled",
    ),
    max_output_tokens: int = typer.Option(
        4000,
        "--max-output-tokens",
        help="OpenAI Responses API max_output_tokens",
    ),
    timeout_seconds: float = typer.Option(60.0, "--timeout", help="OpenAI SDK timeout 秒数"),
    store: bool = typer.Option(False, "--store/--no-store", help="是否允许 OpenAI 远端保存响应"),
    dry_run_prompt: bool = typer.Option(
        False,
        "--dry-run-prompt",
        help="只打印将发送给 LLM 的 prompt/input，不调用 OpenAI SDK",
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help="输出 JSON 或 dry-run prompt 到文件"),
    save_run: bool = typer.Option(
        False,
        "--save-run/--no-save-run",
        help="保存 input/output/metadata/prompt 到 runs-dir",
    ),
    runs_dir: Path = typer.Option(
        Path("llm_runs"),
        "--runs-dir",
        help="--save-run 的保存目录",
    ),
) -> None:
    """把 rule-based assignment draft 整理成供人工复核的 LLM summary draft。"""
    try:
        assignment_markdown = input_path.read_text(encoding="utf-8")
        if dry_run_prompt:
            prompt = load_prompt("assignment_summary")
            payload = build_assignment_summary_input(assignment_markdown)
            _emit_text(render_dry_run_prompt(prompt.text, payload), out)
            return

        settings = _build_llm_settings(
            model=model,
            base_url=base_url,
            api_mode=api_mode,
            api_key_env=api_key_env,
            reasoning_effort=reasoning_effort,
            enable_thinking=enable_thinking,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
            store=store,
        )
        result = summarize_assignment(assignment_markdown, settings=settings)
        if save_run:
            run_dir = save_llm_run(result, runs_dir)
            typer.echo(f"LLM run 已保存：{run_dir}", err=True)
        _emit_json(result.output.model_dump_json(indent=2) + "\n", out)
    except (OSError, LLMInputError, LLMServiceError) as e:
        typer.secho(f"错误: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from e


def _build_llm_settings(
    *,
    model: str | None,
    base_url: str | None,
    api_mode: ApiMode | None,
    api_key_env: str | None,
    reasoning_effort: str | None,
    enable_thinking: bool | None,
    max_output_tokens: int,
    timeout_seconds: float,
    store: bool,
) -> OpenAISettings:
    if max_output_tokens <= 0:
        raise typer.BadParameter("--max-output-tokens 必须是正整数")
    if timeout_seconds <= 0:
        raise typer.BadParameter("--timeout 必须是正数")
    return OpenAISettings.from_env(
        model=model,
        base_url=base_url,
        api_mode=api_mode,
        api_key_env=api_key_env,
        reasoning_effort=reasoning_effort,
        enable_thinking=enable_thinking,
        max_output_tokens=max_output_tokens,
        timeout_seconds=timeout_seconds,
        store=store,
    )


def _emit_json(payload: str, out: Path | None) -> None:
    if out is None:
        typer.echo(payload, nl=False)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")
    typer.echo(f"已写入 {out}")


def _emit_text(text: str, out: Path | None) -> None:
    if out is None:
        typer.echo(text, nl=False)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    typer.echo(f"已写入 {out}")
