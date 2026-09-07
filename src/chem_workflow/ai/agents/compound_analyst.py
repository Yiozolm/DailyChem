"""Read-only multi-tool compound analyst Agent."""

from __future__ import annotations

from agents import Agent, Model

from chem_workflow.ai.schemas import CompoundAnalysisDraft, OpenAISettings
from chem_workflow.ai.sdk.bootstrap import build_agent_model, build_model_settings
from chem_workflow.ai.tools import READ_ONLY_CHEMISTRY_TOOLS

_INSTRUCTIONS = """You are a conservative chemistry workflow assistant.
Use only the supplied input and read-only tools. Never invent analytical values or claim that an
assignment is confirmed. Return a draft with evidence, warnings, and a manual review checklist.
"""


def build_compound_analyst(
    settings: OpenAISettings,
    *,
    model: Model | str | None = None,
) -> Agent[None]:
    """Create the read-only pilot Agent using SDK-native tools and output schema."""
    return Agent(
        name="compound_analyst",
        instructions=_INSTRUCTIONS,
        model=model or build_agent_model(settings),
        model_settings=build_model_settings(settings),
        tools=list(READ_ONLY_CHEMISTRY_TOOLS),
        output_type=CompoundAnalysisDraft,
    )


__all__ = ["build_compound_analyst"]
