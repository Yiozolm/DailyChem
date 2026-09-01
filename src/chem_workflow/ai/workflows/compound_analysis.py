"""Read-only multi-tool compound-analysis pilot workflow."""

from __future__ import annotations

import json

from agents import Model, RunConfig, Runner

from chem_workflow.ai.agents.compound_analyst import build_compound_analyst
from chem_workflow.ai.schemas import CompoundAnalysisDraft, LLMServiceError, OpenAISettings


def analyze_compound(
    *,
    smiles: str,
    question: str,
    settings: OpenAISettings,
    model: Model | str | None = None,
) -> CompoundAnalysisDraft:
    """Run the read-only compound-analysis pilot with no write-capable tools."""
    payload = json.dumps(
        {"smiles": smiles, "question": question},
        ensure_ascii=False,
        sort_keys=True,
    )
    agent = build_compound_analyst(settings, model=model)
    try:
        result = Runner.run_sync(
            agent,
            payload,
            run_config=RunConfig(
                workflow_name="compound_analysis",
                trace_metadata={"task": "compound_analysis"},
                tracing_disabled=settings.base_url is not None,
            ),
        )
        output = result.final_output
        return (
            output
            if isinstance(output, CompoundAnalysisDraft)
            else CompoundAnalysisDraft.model_validate(output)
        )
    except Exception as e:  # noqa: BLE001 - Agents SDK wraps provider-specific exceptions.
        raise LLMServiceError(f"Agent SDK compound analysis 失败：{e}") from e


__all__ = ["analyze_compound"]
