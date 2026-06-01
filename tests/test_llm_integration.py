"""Optional integration tests for the Phase 9 LLM layer.

These call the real OpenAI (or OpenAI-compatible) API and are skipped by default. Enable them with:

```bash
CHEMWF_RUN_OPENAI_INTEGRATION=1 OPENAI_API_KEY=... uv run pytest -m integration
```
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from chem_workflow.llm import draft_experiment_record
from chem_workflow.llm_models import OpenAISettings, resolve_api_key
from chem_workflow.records import load_reaction_record

FIXTURES = Path(__file__).resolve().parents[1] / "examples"
RECORD_FIXTURE = FIXTURES / "raw" / "experiment_record_example.yaml"

_INTEGRATION_ENABLED = os.environ.get("CHEMWF_RUN_OPENAI_INTEGRATION") and resolve_api_key(
    OpenAISettings.from_env()
)


@pytest.mark.integration
@pytest.mark.skipif(
    not _INTEGRATION_ENABLED,
    reason="set CHEMWF_RUN_OPENAI_INTEGRATION and a valid API key to run",
)
def test_draft_experiment_record_real_api() -> None:
    record = load_reaction_record(RECORD_FIXTURE)
    settings = OpenAISettings.from_env()

    result = draft_experiment_record(record, settings=settings)

    assert result.output.status == "draft"
    assert result.output.markdown.strip()
    assert result.metadata.task == "experiment_record_en"
