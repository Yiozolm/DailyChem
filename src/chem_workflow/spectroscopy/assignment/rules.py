"""Load and validate packaged NMR assignment rules."""

from __future__ import annotations

from pathlib import Path

import yaml

from chem_workflow.core.resources import resource_path
from chem_workflow.spectroscopy.assignment.models import AssignmentError, AssignmentRule
from chem_workflow.spectroscopy.nmr.parsing import normalize_multiplicity

DEFAULT_RULES_PATH = resource_path("assignment_rules", "nmr_1h_rules.yaml")
DEFAULT_13C_RULES_PATH = resource_path("assignment_rules", "nmr_13c_rules.yaml")

_FALLBACK_RULES: tuple[dict[str, object], ...] = (
    {
        "id": "aromatic_H",
        "label": "aromatic H",
        "shift_range": [6.0, 8.5],
        "description": "aromatic proton",
        "required_features": ["aromatic_H"],
        "multiplicities": ["m", "d", "t", "dd", "td", "br m"],
    },
    {
        "id": "alkyl_CH3",
        "label": "alkyl CH3",
        "shift_range": [0.7, 1.6],
        "description": "aliphatic methyl proton",
        "required_features": ["alkyl_CH3"],
        "multiplicities": ["s", "d", "t", "m"],
        "expected_integrations": [3, 6, 9],
    },
    {
        "id": "ethyl_CH3",
        "label": "ethyl CH3",
        "shift_range": [0.8, 1.4],
        "description": "methyl group in an ethyl fragment",
        "required_features": ["ethyl_CH3"],
        "multiplicities": ["t"],
        "expected_integrations": [3],
    },
    {
        "id": "ethyl_CH2",
        "label": "ethyl CH2",
        "shift_range": [2.1, 4.5],
        "description": "methylene group in an ethyl fragment",
        "required_features": ["ethyl_CH2"],
        "multiplicities": ["q", "m"],
        "expected_integrations": [2],
    },
    {
        "id": "tert_butyl_CH3",
        "label": "tert-butyl CH3",
        "shift_range": [0.9, 1.6],
        "description": "equivalent methyl groups in a tert-butyl fragment",
        "required_features": ["tert_butyl_CH3"],
        "multiplicities": ["s"],
        "expected_integrations": [9],
    },
    {
        "id": "OCH3",
        "label": "OCH3",
        "shift_range": [3.2, 4.2],
        "description": "methoxy proton",
        "required_features": ["OCH3"],
        "multiplicities": ["s"],
        "expected_integrations": [3],
    },
    {
        "id": "OCH2",
        "label": "OCH2",
        "shift_range": [3.3, 4.6],
        "description": "methylene next to oxygen",
        "required_features": ["OCH2"],
        "multiplicities": ["q", "t", "m"],
        "expected_integrations": [2],
    },
    {
        "id": "aldehyde_H",
        "label": "aldehyde H",
        "shift_range": [9.0, 10.5],
        "description": "aldehyde proton",
        "required_features": ["aldehyde_H"],
        "multiplicities": ["s", "d"],
        "expected_integrations": [1],
    },
    {
        "id": "alkene_H",
        "label": "alkene H",
        "shift_range": [4.5, 6.8],
        "description": "alkene proton",
        "required_features": ["alkene_H"],
        "multiplicities": ["m", "d", "dd", "dt"],
    },
    {
        "id": "acidic_H",
        "label": "acidic / exchangeable H",
        "shift_range": [0.5, 13.0],
        "description": "potentially exchangeable OH / NH / SH proton; handle cautiously",
        "required_features": ["acidic_H"],
        "multiplicities": ["br", "br s", "s"],
        "expected_integrations": [1],
        "warn_if_missing": False,
    },
)

def load_assignment_rules(
    path: str | Path | None = None,
    *,
    default_path: Path = DEFAULT_RULES_PATH,
) -> list[AssignmentRule]:
    """Load NMR assignment rules from YAML.

    If `path` is omitted, `default_path` is used when present; otherwise a small built-in fallback
    keeps installed packages usable.
    """
    raw_rules = _load_raw_rules(path, default_path=default_path)
    return [_parse_rule(raw) for raw in raw_rules]

def _load_raw_rules(
    path: str | Path | None,
    *,
    default_path: Path = DEFAULT_RULES_PATH,
) -> list[dict[str, object]]:
    candidate = Path(path) if path is not None else default_path
    if candidate.exists():
        try:
            payload = yaml.safe_load(candidate.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as e:
            raise AssignmentError(f"无法读取 assignment 规则文件：{candidate}") from e
        if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
            raise AssignmentError("assignment 规则文件必须包含顶层 rules 列表")
        rules = payload["rules"]
        if not all(isinstance(rule, dict) for rule in rules):
            raise AssignmentError("assignment rules 中每一项都必须是 mapping")
        return rules
    if path is not None:
        raise AssignmentError(f"assignment 规则文件不存在：{candidate}")
    return [dict(rule) for rule in _FALLBACK_RULES]

def _parse_rule(raw: dict[str, object]) -> AssignmentRule:
    try:
        shift_range_raw = raw["shift_range"]
        if not isinstance(shift_range_raw, list | tuple) or len(shift_range_raw) != 2:
            raise TypeError("shift_range must contain two values")
        low, high = float(shift_range_raw[0]), float(shift_range_raw[1])
        return AssignmentRule(
            rule_id=str(raw["id"]),
            label=str(raw["label"]),
            shift_range=(min(low, high), max(low, high)),
            description=str(raw.get("description", "")),
            required_features=tuple(str(item) for item in raw.get("required_features", ())),
            multiplicities=tuple(
                normalize_multiplicity(str(item)) for item in raw.get("multiplicities", ())
            ),
            expected_integrations=tuple(
                float(item) for item in raw.get("expected_integrations", ())
            ),
            warn_if_missing=bool(raw.get("warn_if_missing", True)),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise AssignmentError(f"assignment rule 格式错误：{raw!r}") from e

__all__ = ["DEFAULT_13C_RULES_PATH", "DEFAULT_RULES_PATH", "load_assignment_rules"]

