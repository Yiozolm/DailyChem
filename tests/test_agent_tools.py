"""OpenAI Agents SDK read-only tool and pilot workflow tests."""

from __future__ import annotations

from types import SimpleNamespace

from chem_workflow.ai.agents import build_compound_analyst
from chem_workflow.ai.schemas import CompoundAnalysisDraft, OpenAISettings
from chem_workflow.ai.tools import (
    calculate_hrms_text,
    get_structure_metadata,
    normalize_ir_text,
    normalize_uv_text,
)
from chem_workflow.ai.workflows import compound_analysis


def test_read_only_chemistry_tools_delegate_to_domain_functions() -> None:
    metadata = get_structure_metadata("CCO")

    assert metadata["formula"] == "C2H6O"
    assert "HRMS (ESI)" in calculate_hrms_text("CCO", adduct="[M+H]+")
    assert normalize_ir_text("1715, 1600") == "IR (neat) νmax 1715, 1600 cm⁻¹."
    assert normalize_uv_text("254", solvent="MeOH") == "UV-vis (MeOH) λmax 254 nm."


def test_compound_analyst_exposes_only_read_only_tools() -> None:
    settings = OpenAISettings(model="gpt-test")

    agent = build_compound_analyst(settings, model="gpt-test")

    assert {tool.name for tool in agent.tools} == {
        "calculate_hrms_text",
        "get_structure_metadata",
        "normalize_ir_text",
        "normalize_uv_text",
    }


def test_compound_analysis_pilot_uses_sdk_runner(monkeypatch) -> None:  # noqa: ANN001
    captured: dict[str, object] = {}

    def run_sync(agent, input_text, **kwargs):  # noqa: ANN001
        captured.update(agent=agent, input_text=input_text, run_config=kwargs["run_config"])
        return SimpleNamespace(
            final_output=CompoundAnalysisDraft(
                summary_markdown="Draft structure review.",
                evidence=["Tool-backed metadata only."],
                review_checklist=["Confirm against original data."],
            )
        )

    monkeypatch.setattr(compound_analysis.Runner, "run_sync", staticmethod(run_sync))
    output = compound_analysis.analyze_compound(
        smiles="CCO",
        question="Summarize the structure.",
        settings=OpenAISettings(model="gpt-test"),
        model="gpt-test",
    )

    assert output.status == "draft"
    assert captured["agent"].name == "compound_analyst"
    assert '"smiles": "CCO"' in captured["input_text"]
    assert captured["run_config"].workflow_name == "compound_analysis"
