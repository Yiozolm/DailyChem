"""Load and write experiment records."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from chem_workflow.records.models import Language, ReactionRecord, RecordInputError
from chem_workflow.records.rendering import render_experiment_record


def load_reaction_record(path: str | Path) -> ReactionRecord:
    """Load a reaction record from `.yaml`, `.yml`, or `.json`."""
    input_path = Path(path)
    try:
        data = _load_record_data(input_path)
        return ReactionRecord.model_validate(data)
    except RecordInputError:
        raise
    except OSError as e:
        raise RecordInputError(f"无法读取实验记录输入文件：{input_path}") from e
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        raise RecordInputError(f"实验记录输入文件格式错误：{input_path}") from e
    except ValidationError as e:
        raise RecordInputError(f"实验记录字段校验失败：{e}") from e


def write_experiment_record(
    record: ReactionRecord,
    output_path: str | Path,
    language: Language = "en",
) -> Path:
    """Render and write a Markdown experiment record."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_experiment_record(record, language) + "\n", encoding="utf-8")
    return path


def render_record_yaml(record: ReactionRecord) -> str:
    """Serialize a validated record for editing or archival."""
    payload = record.model_dump(mode="json", by_alias=True, exclude_none=True)
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def _load_record_data(path: Path) -> dict[str, object]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        raw = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        raw = yaml.safe_load(text)
    else:
        raise RecordInputError("实验记录输入只支持 .yaml / .yml / .json 文件")

    if not isinstance(raw, dict):
        raise RecordInputError("实验记录输入必须是顶层 mapping/object")
    if not all(isinstance(key, str) for key in raw):
        raise RecordInputError("实验记录输入的顶层字段名必须都是字符串")
    return raw


__all__ = ["load_reaction_record", "render_record_yaml", "write_experiment_record"]
