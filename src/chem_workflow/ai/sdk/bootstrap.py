"""Configure OpenAI Agents SDK models from project settings."""

from __future__ import annotations

from agents import Model, ModelSettings, OpenAIChatCompletionsModel, OpenAIResponsesModel
from openai import AsyncOpenAI

from chem_workflow.ai.schemas import (
    LLMInputError,
    OpenAISettings,
    load_dotenv_if_present,
    resolve_api_key,
    validate_openai_base_url,
)


def ensure_openai_api_key(settings: OpenAISettings | None = None) -> str:
    """Resolve the configured provider key or raise a user-facing error."""
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


def build_agent_model(settings: OpenAISettings) -> Model:
    """Build an Agents SDK model without issuing a model request."""
    validate_openai_base_url(settings.base_url)
    kwargs: dict[str, object] = {
        "api_key": ensure_openai_api_key(settings),
        "timeout": settings.timeout_seconds,
    }
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    client = AsyncOpenAI(**kwargs)
    if settings.api_mode == "chat-completions":
        return OpenAIChatCompletionsModel(model=settings.model, openai_client=client)
    return OpenAIResponsesModel(model=settings.model, openai_client=client)


def build_model_settings(settings: OpenAISettings) -> ModelSettings:
    """Map project settings to Agents SDK model settings."""
    extra_body = {"thinking": {"type": "enabled"}} if settings.enable_thinking else None
    reasoning = {"effort": settings.reasoning_effort} if settings.reasoning_effort else None
    return ModelSettings(
        max_tokens=settings.max_output_tokens,
        reasoning=reasoning,  # type: ignore[arg-type]
        extra_body=extra_body,
        store=settings.store,
    )


__all__ = ["build_agent_model", "build_model_settings", "ensure_openai_api_key"]
