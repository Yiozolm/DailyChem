"""Tests for local GLM-OCR parsing, client payloads, and WSL command construction."""

from __future__ import annotations

import json
from unittest.mock import patch

from chem_workflow.core.config import OCRConfig
from chem_workflow.ocr import (
    GLMOCRClient,
    OCRImage,
    OCRRecordDraft,
    OCRRuntimeManager,
    parse_ocr_content,
)


def test_parse_fenced_ocr_json_and_map_to_form() -> None:
    content = """```json
    {
      "compound_id": {"value": "C101", "source_text": "编号 C101"},
      "starting_materials": [{
        "name": "benzoic acid",
        "amount": "1.0 mmol",
        "source_text": "benzoic acid 1.0 mmol"
      }],
      "temperature": {"value": "0 °C", "source_text": "0 °C"},
      "yield_percent": {"value": "72%", "source_text": "yield 72%"},
      "raw_text": "编号 C101; benzoic acid 1.0 mmol; yield 72%"
    }
    ```"""

    draft = parse_ocr_content(content, page_count=2)

    assert isinstance(draft, OCRRecordDraft)
    assert draft.page_count == 2
    assert draft.compound_id.value == "C101"
    assert draft.starting_materials[0].as_form_line() == "benzoic acid | 1.0 mmol"
    assert draft.form_values()["yield_percent"] == "72%"


def test_parse_accepts_record_wrapper_and_plain_strings() -> None:
    draft = parse_ocr_content(
        json.dumps(
            {
                "record": {
                    "product_name": "product A",
                    "reagents": ["Et3N"],
                    "unmapped_text": "extra note",
                }
            }
        )
    )

    assert draft.product_name.value == "product A"
    assert draft.reagents[0].name.value == "Et3N"
    assert draft.unmapped_text == ["extra note"]


def test_client_builds_image_chat_payload() -> None:
    client = GLMOCRClient(model="zai-org/GLM-OCR")
    captured: dict[str, object] = {}

    def fake_request(
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        captured.update({"method": method, "path": path, "payload": payload})
        return {"choices": [{"message": {"content": "{}"}}]}

    with patch.object(client, "_request", side_effect=fake_request):
        response = client.recognize([OCRImage("page.jpg", b"abc")], "return JSON")

    assert response["choices"]
    payload = captured["payload"]
    assert isinstance(payload, dict)
    content = payload["messages"][0]["content"]
    assert content[0]["text"] == "return JSON"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_runtime_command_uses_configured_distro_and_model() -> None:
    manager = OCRRuntimeManager(
        OCRConfig(
            wsl_distribution="Ubuntu-24.04",
            model_dir="~/models/GLM-OCR",
            vllm_env_dir="~/dailychem-ocr/.venv",
            vllm_log_path="~/dailychem-ocr/vllm.log",
            model_revision="abc123",
        )
    )

    command = manager.build_start_command()
    shell = command[-1]

    assert command[:4] == ["wsl.exe", "-d", "Ubuntu-24.04", "--"]
    assert "vllm serve \"$HOME/models/GLM-OCR\"" in shell
    assert "--served-model-name 'zai-org/GLM-OCR'" in shell
    assert "--revision 'abc123'" in shell


def test_ocr_config_defaults_are_safe() -> None:
    config = OCRConfig()
    assert config.host == "127.0.0.1"
    assert config.port == 8000
    assert config.request_timeout_seconds > 0
