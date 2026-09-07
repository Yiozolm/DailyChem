"""Packaged prompt and assignment-rule resource tests."""

from __future__ import annotations

import pytest

from chem_workflow.assignment import DEFAULT_13C_RULES_PATH, DEFAULT_RULES_PATH
from chem_workflow.core.resources import ResourceError, read_resource_text, resource_path
from chem_workflow.llm import load_prompt


def test_packaged_prompts_are_readable() -> None:
    prompt = load_prompt("experiment_record_en")

    assert prompt.version == "2026-05-18-v1"
    assert prompt.path == resource_path("prompts", "experiment_record_en.txt")
    assert "Output-Schema: ExperimentRecordDraft" in prompt.text


def test_packaged_assignment_rules_are_readable() -> None:
    assert resource_path("assignment_rules", "nmr_1h_rules.yaml") == DEFAULT_RULES_PATH
    assert resource_path("assignment_rules", "nmr_13c_rules.yaml") == DEFAULT_13C_RULES_PATH
    assert "aromatic_H" in read_resource_text("assignment_rules", "nmr_1h_rules.yaml")
    assert "carbonyl_C" in read_resource_text("assignment_rules", "nmr_13c_rules.yaml")


def test_resource_path_rejects_traversal() -> None:
    with pytest.raises(ResourceError, match="非法资源路径片段"):
        resource_path("..", "secret.txt")


def test_missing_resource_has_actionable_error() -> None:
    with pytest.raises(ResourceError, match="找不到内置资源"):
        read_resource_text("prompts", "missing.txt")
