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
    OCRService,
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


def test_parse_preserves_reaction_steps_and_repairs_material_roles() -> None:
    draft = parse_ocr_content(
        json.dumps(
            {
                "starting_materials": [
                    {
                        "name": "K₂CO₃",
                        "amount": "3.00 mmol",
                        "source_text": "K₂CO₃ 3.00 mmol",
                    },
                    {"name": "DMF", "amount": "1.5 mL", "source_text": "DMF 1.5 mL"},
                ],
                "procedure": {
                    "value": "To the mixture of I, K₂CO₃ and DMF, add MeI dropwise.",
                    "source_text": "To the mixture of I, K₂CO₃ and DMF, add MeI dropwise.",
                },
                "raw_text": (
                    "Compound I M 332.3 1.50 mmol 0.5 g\n"
                    "To the mixture of I, K2CO3 and DMF, add MeI dropwise."
                ),
            }
        )
    )

    assert [item.name.value for item in draft.starting_materials] == ["compound I"]
    assert [item.name.value for item in draft.reagents] == ["K₂CO₃", "MeI"]
    assert draft.solvent.value == "DMF"
    assert draft.procedure.value.startswith("To the mixture")
    assert draft.form_values()["procedure"].startswith("To the mixture")
    assert any("重新分类" in warning for warning in draft.warnings)


def test_prompt_explains_substrate_reagent_roles_and_procedure() -> None:
    from chem_workflow.ocr.service import OCR_PROMPT

    assert "不要把 K2CO3" in OCR_PROMPT
    assert "procedure" in OCR_PROMPT
    assert "workup" in OCR_PROMPT


def test_labelled_substrate_is_not_left_in_reagents() -> None:
    draft = parse_ocr_content(
        json.dumps(
            {
                "reagents": ["compound II", "DBU", "CuI"],
                "raw_text": "I + II, DBU, CuI in MeCN",
            }
        )
    )

    assert [item.name.value for item in draft.starting_materials] == ["compound II"]
    assert [item.name.value for item in draft.reagents] == ["DBU", "CuI"]


def test_parse_cleans_table_values_and_common_page_two_roles() -> None:
    draft = parse_ocr_content(
        json.dumps(
            {
                "compound_id": "346.3",
                "product_name": "DBU",
                "smiles": ["CuCl2", "DBU", "MeCN"],
                "starting_materials": ["I", "II", "CuCl2", "DBU", "MeCN"],
                "raw_text": "I 346.3\nII 102.56\nCuCl2\nDBU\nMeCN",
            }
        )
    )

    assert draft.compound_id.value is None
    assert draft.product_name.value is None
    assert draft.smiles.value is None
    assert [item.name.value for item in draft.starting_materials] == ["I", "II"]
    assert [item.name.value for item in draft.reagents] == ["CuCl2", "DBU"]
    assert draft.solvent.value == "MeCN"


def test_procedure_falls_back_to_action_lines_in_raw_text() -> None:
    draft = parse_ocr_content(
        json.dumps(
            {
                "raw_text": (
                    "15:36 Add MeI dropwise to the mixture.\n"
                    "22:47 Quench with water and extract with EtOAc."
                )
            }
        )
    )

    assert draft.procedure.value == "15:36 Add MeI dropwise to the mixture."
    assert any("raw_text" in warning for warning in draft.warnings)


def test_service_uses_transcription_pass_when_structured_output_is_incomplete() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.prompts: list[str] = []
            self.responses = [
                json.dumps(
                    {
                        "starting_materials": ["K2CO3"],
                        "procedure": "Add MeI dropwise.",
                    }
                ),
                json.dumps(
                    {
                        "raw_text": (
                            "15:36 Add MeI dropwise.\n"
                            "Quench with water and extract with EtOAc.\n"
                            "Column: 30% EtOAc in hexane.\n"
                            "Yield: 10 mg (20%)."
                        )
                    }
                ),
            ]

        def recognize(self, images, prompt):  # noqa: ANN001
            self.prompts.append(prompt)
            return {"content": self.responses.pop(0)}

        def extract_content(self, response):  # noqa: ANN001
            return response["content"]

    client = FakeClient()
    draft, raw_response, _ = OCRService(client).recognize([OCRImage("page.jpg", b"abc")])

    assert len(client.prompts) == 2
    assert draft.workup.value == "Quench with water and extract with EtOAc."
    assert draft.purification.value == "Column: 30% EtOAc in hexane."
    assert draft.yield_mass.value == "10 mg"
    assert draft.yield_percent.value == "20%"
    assert set(raw_response) == {"structured", "transcription"}


def test_runtime_client_uses_exposed_model_alias() -> None:
    manager = OCRRuntimeManager(OCRConfig(model_id="zai-org/GLM-OCR"))
    manager.active_model = "glm-ocr"

    assert manager.client().model == "glm-ocr"


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
