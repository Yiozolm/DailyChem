"""Agent definitions for schema-valid chemistry drafting tasks."""

from __future__ import annotations

from agents import Agent, Model
from pydantic import BaseModel

from chem_workflow.ai.schemas import OpenAISettings, PromptTemplate
from chem_workflow.ai.sdk.bootstrap import build_agent_model, build_model_settings


def build_generation_agent(
    *,
    task: str,
    settings: OpenAISettings,
    prompt: PromptTemplate,
    output_type: type[BaseModel],
    model: Model | None = None,
) -> Agent[None]:
    """Create one structured-output Agent using the selected SDK-native model."""
    return Agent(
        name=task,
        instructions=prompt.text,
        model=model or build_agent_model(settings),
        model_settings=build_model_settings(settings),
        output_type=output_type,
    )


__all__ = ["build_generation_agent"]
