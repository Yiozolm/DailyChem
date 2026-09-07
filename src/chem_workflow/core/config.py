"""Phase 12 configuration for chemwf.

A small, optional ``.chemwf.toml`` in the working directory provides defaults for the Streamlit UI
(and any future CLI defaults). Missing file or missing keys fall back to built-in defaults, so the
tool always runs without configuration.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ValidationError

CONFIG_FILENAME = ".chemwf.toml"


class ConfigError(ValueError):
    """配置文件解析或校验失败时抛出。错误信息会展示给用户，应包含可操作建议。"""


class ChemwfConfig(BaseModel):
    """User-tunable defaults. All fields have safe built-in defaults."""

    default_frequency_1h: float = 400.0
    default_frequency_13c: float = 101.0
    default_solvent: str = "CDCl3"
    default_ionization: str = "ESI"
    default_adduct: str = "[M+Na]+"
    db_path: str = "data/chem_workflow.sqlite"
    llm_model: str | None = None
    project_dir: str = "."


CONFIG_TEMPLATE = """\
# chemwf 本地配置（可选）。删除任意行即可回退到内置默认值。

# NMR 默认频率与溶剂
default_frequency_1h = 400.0
default_frequency_13c = 101.0
default_solvent = "CDCl3"

# MS / HRMS 默认电离方式与加合
default_ionization = "ESI"
default_adduct = "[M+Na]+"

# 本地历史数据库路径
db_path = "data/chem_workflow.sqlite"

# LLM 默认模型（留空则用 CHEMWF_OPENAI_MODEL 或 SDK 默认）
# llm_model = "gpt-5.4-mini"

# 项目归档根目录
project_dir = "."
"""


def find_config_path(start: str | Path | None = None) -> Path | None:
    """Return the nearest ``.chemwf.toml`` at or above ``start`` (cwd by default), or None."""
    base = Path(start).resolve() if start is not None else Path.cwd().resolve()
    for directory in (base, *base.parents):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_config(path: str | Path | None = None) -> ChemwfConfig:
    """Load configuration from ``path`` (or the nearest ``.chemwf.toml``); defaults if absent."""
    config_path = Path(path) if path is not None else find_config_path()
    if config_path is None:
        return ChemwfConfig()
    if not Path(config_path).is_file():
        raise ConfigError(f"找不到配置文件：{config_path}")
    try:
        data = tomllib.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"配置文件无法解析：{config_path}（{e}）") from e
    try:
        return ChemwfConfig.model_validate(data)
    except ValidationError as e:
        raise ConfigError(f"配置文件字段非法：{config_path}\n{e}") from e
