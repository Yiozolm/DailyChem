"""Rule-based 1H NMR assignment assistance.

This module intentionally produces *candidates*, not final assignments. The output is designed for
manual review: every peak keeps a status and the renderer repeats that the draft is not proof.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from rdkit import Chem
from rdkit.Chem import rdchem

from chem_workflow.nmr import NMRPeak, NMRSpectrum, normalize_multiplicity
from chem_workflow.structure import mol_info

AssignmentStatus = Literal["candidate", "needs_review", "confirmed"]
WarningSeverity = Literal["info", "warning", "risk"]

DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "rules" / "nmr_1h_rules.yaml"

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


class AssignmentError(ValueError):
    """Raised when rule loading or assignment drafting fails."""


@dataclass(frozen=True)
class AssignmentRule:
    """A simple 1H NMR shift rule."""

    rule_id: str
    label: str
    shift_range: tuple[float, float]
    description: str
    required_features: tuple[str, ...] = ()
    multiplicities: tuple[str, ...] = ()
    expected_integrations: tuple[float, ...] = ()
    warn_if_missing: bool = True


@dataclass(frozen=True)
class DetectedFeature:
    """A structural feature detected from an RDKit molecule."""

    feature_id: str
    label: str
    description: str
    atom_indices: tuple[int, ...]
    proton_count: float | None = None
    caution: str | None = None


@dataclass(frozen=True)
class AssignmentCandidate:
    """A possible assignment for a peak."""

    rule_id: str
    label: str
    description: str
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class PeakAssignment:
    """Assignment draft state for one peak."""

    peak: NMRPeak
    candidates: tuple[AssignmentCandidate, ...]
    status: AssignmentStatus
    selected_label: str | None = None
    manual_note: str | None = None


@dataclass(frozen=True)
class AssignmentWarning:
    """Risk or caution emitted by the assignment assistant."""

    code: str
    message: str
    severity: WarningSeverity = "warning"


@dataclass(frozen=True)
class AssignmentDraft:
    """Rule-based assignment draft for a 1H NMR spectrum."""

    compound_smiles: str
    formula: str
    expected_protons: int
    features: tuple[DetectedFeature, ...]
    peak_assignments: tuple[PeakAssignment, ...]
    warnings: tuple[AssignmentWarning, ...]
    note: str = field(
        default=(
            "Rule-based candidate assignment only. Manual confirmation is required before use in "
            "a report, thesis, paper, or supporting information."
        )
    )


def load_assignment_rules(path: str | Path | None = None) -> list[AssignmentRule]:
    """Load 1H NMR assignment rules from YAML.

    If `path` is omitted, `data/rules/nmr_1h_rules.yaml` is used when present; otherwise a small
    built-in fallback keeps installed packages usable.
    """
    raw_rules = _load_raw_rules(path)
    return [_parse_rule(raw) for raw in raw_rules]


def detect_proton_features(mol: Chem.Mol) -> tuple[DetectedFeature, ...]:
    """Detect common proton-containing structural features with RDKit heuristics."""
    features: list[DetectedFeature] = []
    features.extend(_detect_aromatic_h(mol))
    features.extend(_detect_methoxy(mol))
    features.extend(_detect_oxygen_methylene(mol))
    features.extend(_detect_ethyl(mol))
    features.extend(_detect_tert_butyl(mol))
    features.extend(_detect_alkyl_methyl(mol))
    features.extend(_detect_aldehyde_h(mol))
    features.extend(_detect_alkene_h(mol))
    features.extend(_detect_acidic_h(mol))
    return tuple(_dedupe_features(features))


def assign_1h_nmr(
    mol: Chem.Mol,
    spectrum: NMRSpectrum,
    *,
    rules: list[AssignmentRule] | None = None,
) -> AssignmentDraft:
    """Generate a candidate assignment draft for a 1H NMR spectrum."""
    if spectrum.nucleus != "1H":
        raise AssignmentError("当前 assignment assistant 只支持 1H NMR。")
    if not spectrum.peaks:
        raise AssignmentError("NMR spectrum 没有 peak，无法生成 assignment 草稿。")

    assignment_rules = rules or load_assignment_rules()
    info = mol_info(mol)
    features = detect_proton_features(mol)
    peak_assignments = tuple(
        _assign_peak(peak, assignment_rules, features) for peak in spectrum.peaks
    )
    expected_protons = _expected_proton_count(mol)
    warnings = _build_warnings(
        spectrum=spectrum,
        expected_protons=expected_protons,
        features=features,
        rules=assignment_rules,
        peak_assignments=peak_assignments,
    )
    return AssignmentDraft(
        compound_smiles=str(info["smiles"]),
        formula=str(info["formula"]),
        expected_protons=expected_protons,
        features=features,
        peak_assignments=peak_assignments,
        warnings=warnings,
    )


def render_assignment_draft(draft: AssignmentDraft) -> str:
    """Render an assignment draft as Markdown."""
    lines: list[str] = [
        "# 1H NMR Assignment Draft",
        "",
        "> Candidate assignment only. Manual confirmation is required.",
        "",
        "## Compound",
        "",
        f"- Canonical SMILES: `{draft.compound_smiles}`",
        f"- Formula: {draft.formula}",
        f"- Expected proton count from structure: {draft.expected_protons}",
        "",
        "## Detected structural features",
        "",
    ]
    lines.extend(_render_feature_lines(draft.features))
    lines.extend(["", "## Peak-level candidates", ""])
    lines.extend(_render_assignment_table(draft.peak_assignments))
    lines.extend(["", "## Warnings and review notes", ""])
    lines.extend(_render_warning_lines(draft.warnings))
    lines.extend(["", "## Review status", ""])
    lines.append(
        "All rows start as `candidate` or `needs_review`. Change a row to `confirmed` only after "
        "manual inspection against the structure and original spectrum."
    )
    return "\n".join(lines).rstrip() + "\n"


def assignment_rows_for_review(draft: AssignmentDraft) -> list[dict[str, object]]:
    """Return editable row dictionaries for CLI/UI review tables."""
    rows: list[dict[str, object]] = []
    for assignment in draft.peak_assignments:
        rows.append(
            {
                "peak": _format_peak(assignment.peak),
                "integration": _format_optional_number(assignment.peak.integration),
                "multiplicity": assignment.peak.multiplicity or "",
                "candidates": "; ".join(candidate.label for candidate in assignment.candidates),
                "status": assignment.status,
                "selected_assignment": assignment.selected_label or "",
                "manual_note": assignment.manual_note or "",
            }
        )
    return rows


def _load_raw_rules(path: str | Path | None) -> list[dict[str, object]]:
    candidate = Path(path) if path is not None else DEFAULT_RULES_PATH
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


def _assign_peak(
    peak: NMRPeak,
    rules: list[AssignmentRule],
    features: tuple[DetectedFeature, ...],
) -> PeakAssignment:
    candidates = [
        candidate
        for rule in rules
        if _rule_can_apply_to_structure(rule, features) and _peak_matches_rule_shift(peak, rule)
        if (candidate := _candidate_for_rule(peak, rule, features)) is not None
    ]
    candidates.sort(key=lambda candidate: candidate.confidence, reverse=True)
    selected = candidates[0].label if candidates else None
    status: AssignmentStatus = "candidate" if candidates else "needs_review"
    return PeakAssignment(
        peak=peak,
        candidates=tuple(candidates),
        status=status,
        selected_label=selected,
    )


def _candidate_for_rule(
    peak: NMRPeak,
    rule: AssignmentRule,
    features: tuple[DetectedFeature, ...],
) -> AssignmentCandidate | None:
    evidence = [f"δ within {rule.shift_range[0]:.1f}–{rule.shift_range[1]:.1f} ppm"]
    score = 0.45

    matched_features = _matching_features(rule, features)
    if rule.required_features:
        if not matched_features:
            return None
        labels = ", ".join(feature.label for feature in matched_features)
        evidence.append(f"structure contains {labels}")
        score += 0.25

    if peak.multiplicity and rule.multiplicities:
        peak_mult = normalize_multiplicity(peak.multiplicity)
        if peak_mult in rule.multiplicities:
            evidence.append(f"multiplicity {peak_mult} matches rule")
            score += 0.15

    if (
        peak.integration is not None
        and rule.expected_integrations
        and _integration_matches(peak.integration, rule.expected_integrations)
    ):
        expected = "/".join(_format_optional_number(value) for value in rule.expected_integrations)
        evidence.append(f"integration {peak.integration:g}H matches expected {expected}H")
        score += 0.15

    return AssignmentCandidate(
        rule_id=rule.rule_id,
        label=rule.label,
        description=rule.description,
        confidence=round(min(score, 0.95), 2),
        evidence=tuple(evidence),
    )


def _rule_can_apply_to_structure(
    rule: AssignmentRule,
    features: tuple[DetectedFeature, ...],
) -> bool:
    if not rule.required_features:
        return True
    feature_ids = {feature.feature_id for feature in features}
    return any(feature_id in feature_ids for feature_id in rule.required_features)


def _matching_features(
    rule: AssignmentRule,
    features: tuple[DetectedFeature, ...],
) -> tuple[DetectedFeature, ...]:
    required = set(rule.required_features)
    return tuple(feature for feature in features if feature.feature_id in required)


def _peak_matches_rule_shift(peak: NMRPeak, rule: AssignmentRule) -> bool:
    low, high = rule.shift_range
    if low <= peak.shift_ppm <= high:
        return True
    if peak.shift_range is None:
        return False
    peak_low, peak_high = peak.shift_range
    return peak_low <= high and peak_high >= low


def _integration_matches(value: float, expected_values: tuple[float, ...]) -> bool:
    return any(abs(value - expected) <= 0.35 for expected in expected_values)


def _build_warnings(
    *,
    spectrum: NMRSpectrum,
    expected_protons: int,
    features: tuple[DetectedFeature, ...],
    rules: list[AssignmentRule],
    peak_assignments: tuple[PeakAssignment, ...],
) -> tuple[AssignmentWarning, ...]:
    warnings: list[AssignmentWarning] = []
    warnings.extend(_integration_warnings(spectrum, expected_protons))
    warnings.extend(_aromatic_warnings(spectrum, features))
    warnings.extend(_unexplained_peak_warnings(peak_assignments))
    warnings.extend(_missing_feature_warnings(rules, features, peak_assignments))
    warnings.extend(_feature_cautions(features))
    if not warnings:
        warnings.append(
            AssignmentWarning(
                code="manual_review_required",
                message="未发现明显规则风险；仍需人工核对原始谱图和结构。",
                severity="info",
            )
        )
    return tuple(warnings)


def _integration_warnings(
    spectrum: NMRSpectrum,
    expected_protons: int,
) -> list[AssignmentWarning]:
    values = [peak.integration for peak in spectrum.peaks if peak.integration is not None]
    if not values:
        return [
            AssignmentWarning(
                code="integration_missing",
                message="peak list 没有积分信息，无法检查总氢数一致性。",
                severity="info",
            )
        ]
    total = sum(values)
    tolerance = max(1.0, expected_protons * 0.2)
    if abs(total - expected_protons) <= tolerance:
        return []
    return [
        AssignmentWarning(
            code="integration_total_mismatch",
            message=(
                f"积分总和约 {total:g}H，但结构预期 {expected_protons}H；"
                "请检查归一化、杂质峰或漏峰。"
            ),
            severity="risk",
        )
    ]


def _aromatic_warnings(
    spectrum: NMRSpectrum,
    features: tuple[DetectedFeature, ...],
) -> list[AssignmentWarning]:
    has_aromatic = any(feature.feature_id == "aromatic_H" for feature in features)
    aromatic_peaks = [peak for peak in spectrum.peaks if 6.0 <= peak.shift_ppm <= 8.5]
    if has_aromatic and not aromatic_peaks:
        return [
            AssignmentWarning(
                code="missing_aromatic_region",
                message="结构含 aromatic H，但 peak list 中没有 6.0–8.5 ppm 区域峰。",
                severity="risk",
            )
        ]
    if not has_aromatic and aromatic_peaks:
        return [
            AssignmentWarning(
                code="unexpected_aromatic_region",
                message="结构未检测到 aromatic H，但 peak list 中出现 aromatic 区域峰。",
                severity="warning",
            )
        ]
    return []


def _unexplained_peak_warnings(
    peak_assignments: tuple[PeakAssignment, ...],
) -> list[AssignmentWarning]:
    warnings: list[AssignmentWarning] = []
    for assignment in peak_assignments:
        if assignment.candidates:
            continue
        integration = assignment.peak.integration
        if integration is not None and integration >= 2:
            warnings.append(
                AssignmentWarning(
                    code="unexplained_strong_peak",
                    message=(
                        f"{_format_peak(assignment.peak)} 没有规则候选，且积分约 {integration:g}H。"
                    ),
                    severity="warning",
                )
            )
    return warnings


def _missing_feature_warnings(
    rules: list[AssignmentRule],
    features: tuple[DetectedFeature, ...],
    peak_assignments: tuple[PeakAssignment, ...],
) -> list[AssignmentWarning]:
    feature_ids = {feature.feature_id for feature in features}
    warnings: list[AssignmentWarning] = []
    for rule in rules:
        if not rule.warn_if_missing or not rule.required_features:
            continue
        if not any(feature_id in feature_ids for feature_id in rule.required_features):
            continue
        if any(
            candidate.rule_id == rule.rule_id
            for assignment in peak_assignments
            for candidate in assignment.candidates
        ):
            continue
        warnings.append(
            AssignmentWarning(
                code="missing_expected_feature_peak",
                message=f"结构检测到 {rule.label}，但未找到符合规则区间的候选 peak。",
                severity="warning",
            )
        )
    return warnings


def _feature_cautions(features: tuple[DetectedFeature, ...]) -> list[AssignmentWarning]:
    return [
        AssignmentWarning(
            code=f"caution_{feature.feature_id}",
            message=f"{feature.label}: {feature.caution}",
            severity="info",
        )
        for feature in features
        if feature.caution
    ]


def _detect_aromatic_h(mol: Chem.Mol) -> list[DetectedFeature]:
    atoms = tuple(
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() == 6 and atom.GetIsAromatic() and _total_h(atom) > 0
    )
    if not atoms:
        return []
    return [
        DetectedFeature(
            feature_id="aromatic_H",
            label="aromatic H",
            description="aromatic carbon bearing hydrogen",
            atom_indices=atoms,
            proton_count=float(sum(_total_h(mol.GetAtomWithIdx(idx)) for idx in atoms)),
        )
    ]


def _detect_methoxy(mol: Chem.Mol) -> list[DetectedFeature]:
    features: list[DetectedFeature] = []
    for atom in mol.GetAtoms():
        if not _is_carbon_h(atom, 3):
            continue
        oxygen_neighbors = [
            neighbor for neighbor in atom.GetNeighbors() if neighbor.GetAtomicNum() == 8
        ]
        for oxygen in oxygen_neighbors:
            features.append(
                DetectedFeature(
                    feature_id="OCH3",
                    label="OCH3",
                    description="methyl group attached to oxygen",
                    atom_indices=(oxygen.GetIdx(), atom.GetIdx()),
                    proton_count=3.0,
                )
            )
    return features


def _detect_oxygen_methylene(mol: Chem.Mol) -> list[DetectedFeature]:
    features: list[DetectedFeature] = []
    for atom in mol.GetAtoms():
        if not _is_carbon_h(atom, 2):
            continue
        oxygen_neighbors = [
            neighbor for neighbor in atom.GetNeighbors() if neighbor.GetAtomicNum() == 8
        ]
        for oxygen in oxygen_neighbors:
            features.append(
                DetectedFeature(
                    feature_id="OCH2",
                    label="OCH2",
                    description="methylene group attached to oxygen",
                    atom_indices=(oxygen.GetIdx(), atom.GetIdx()),
                    proton_count=2.0,
                )
            )
    return features


def _detect_ethyl(mol: Chem.Mol) -> list[DetectedFeature]:
    features: list[DetectedFeature] = []
    seen_pairs: set[tuple[int, int]] = set()
    for methyl in mol.GetAtoms():
        if not _is_carbon_h(methyl, 3):
            continue
        for methylene in methyl.GetNeighbors():
            if not _is_carbon_h(methylene, 2):
                continue
            pair = (methyl.GetIdx(), methylene.GetIdx())
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            features.append(
                DetectedFeature(
                    feature_id="ethyl_CH3",
                    label="ethyl CH3",
                    description="methyl side of an ethyl fragment",
                    atom_indices=(methyl.GetIdx(), methylene.GetIdx()),
                    proton_count=3.0,
                )
            )
            features.append(
                DetectedFeature(
                    feature_id="ethyl_CH2",
                    label="ethyl CH2",
                    description="methylene side of an ethyl fragment",
                    atom_indices=(methylene.GetIdx(), methyl.GetIdx()),
                    proton_count=2.0,
                )
            )
    return features


def _detect_tert_butyl(mol: Chem.Mol) -> list[DetectedFeature]:
    features: list[DetectedFeature] = []
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6 or atom.GetIsAromatic():
            continue
        methyl_neighbors = [
            neighbor.GetIdx() for neighbor in atom.GetNeighbors() if _is_carbon_h(neighbor, 3)
        ]
        if len(methyl_neighbors) >= 3:
            features.append(
                DetectedFeature(
                    feature_id="tert_butyl_CH3",
                    label="tert-butyl CH3",
                    description="three methyl groups attached to a quaternary carbon",
                    atom_indices=(atom.GetIdx(), *tuple(methyl_neighbors[:3])),
                    proton_count=9.0,
                )
            )
    return features


def _detect_alkyl_methyl(mol: Chem.Mol) -> list[DetectedFeature]:
    features: list[DetectedFeature] = []
    for atom in mol.GetAtoms():
        if not _is_carbon_h(atom, 3):
            continue
        if any(
            neighbor.GetAtomicNum() in {7, 8, 9, 16, 17, 35, 53} for neighbor in atom.GetNeighbors()
        ):
            continue
        features.append(
            DetectedFeature(
                feature_id="alkyl_CH3",
                label="alkyl CH3",
                description="aliphatic methyl group",
                atom_indices=(atom.GetIdx(),),
                proton_count=3.0,
            )
        )
    return features


def _detect_aldehyde_h(mol: Chem.Mol) -> list[DetectedFeature]:
    features: list[DetectedFeature] = []
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6 or _total_h(atom) != 1:
            continue
        if any(_is_double_bond_to_oxygen(bond, atom) for bond in atom.GetBonds()):
            features.append(
                DetectedFeature(
                    feature_id="aldehyde_H",
                    label="aldehyde H",
                    description="formyl carbon bearing one hydrogen",
                    atom_indices=(atom.GetIdx(),),
                    proton_count=1.0,
                )
            )
    return features


def _detect_alkene_h(mol: Chem.Mol) -> list[DetectedFeature]:
    atoms: set[int] = set()
    for bond in mol.GetBonds():
        if bond.GetBondType() != rdchem.BondType.DOUBLE:
            continue
        begin = bond.GetBeginAtom()
        end = bond.GetEndAtom()
        if begin.GetAtomicNum() == 6 and end.GetAtomicNum() == 6:
            for atom in (begin, end):
                if not atom.GetIsAromatic() and _total_h(atom) > 0:
                    atoms.add(atom.GetIdx())
    if not atoms:
        return []
    return [
        DetectedFeature(
            feature_id="alkene_H",
            label="alkene H",
            description="vinylic proton on a non-aromatic C=C bond",
            atom_indices=tuple(sorted(atoms)),
            proton_count=float(sum(_total_h(mol.GetAtomWithIdx(idx)) for idx in atoms)),
        )
    ]


def _detect_acidic_h(mol: Chem.Mol) -> list[DetectedFeature]:
    atoms = tuple(
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() in {7, 8, 16} and _total_h(atom) > 0
    )
    if not atoms:
        return []
    return [
        DetectedFeature(
            feature_id="acidic_H",
            label="acidic / exchangeable H",
            description="heteroatom-bound proton",
            atom_indices=atoms,
            proton_count=float(sum(_total_h(mol.GetAtomWithIdx(idx)) for idx in atoms)),
            caution="exchangeable OH/NH/SH peaks can be broad, concentration-dependent, or absent.",
        )
    ]


def _dedupe_features(features: list[DetectedFeature]) -> list[DetectedFeature]:
    seen: set[tuple[str, tuple[int, ...]]] = set()
    unique: list[DetectedFeature] = []
    for feature in features:
        key = (feature.feature_id, tuple(sorted(feature.atom_indices)))
        if key in seen:
            continue
        seen.add(key)
        unique.append(feature)
    return unique


def _expected_proton_count(mol: Chem.Mol) -> int:
    with_h = Chem.AddHs(mol)
    return sum(1 for atom in with_h.GetAtoms() if atom.GetAtomicNum() == 1)


def _is_carbon_h(atom: Chem.Atom, hydrogen_count: int) -> bool:
    return (
        atom.GetAtomicNum() == 6 and not atom.GetIsAromatic() and _total_h(atom) == hydrogen_count
    )


def _total_h(atom: Chem.Atom) -> int:
    return int(atom.GetTotalNumHs())


def _is_double_bond_to_oxygen(bond: Chem.Bond, carbon: Chem.Atom) -> bool:
    if bond.GetBondType() != rdchem.BondType.DOUBLE:
        return False
    other = bond.GetOtherAtom(carbon)
    return other.GetAtomicNum() == 8


def _render_feature_lines(features: tuple[DetectedFeature, ...]) -> list[str]:
    if not features:
        return ["- No supported proton features detected."]
    return [
        (
            f"- **{feature.label}** — atoms {list(feature.atom_indices)}"
            f"{_feature_proton_suffix(feature)}"
        )
        for feature in features
    ]


def _feature_proton_suffix(feature: DetectedFeature) -> str:
    if feature.proton_count is None:
        return ""
    return f", expected {feature.proton_count:g}H"


def _render_assignment_table(assignments: tuple[PeakAssignment, ...]) -> list[str]:
    lines = [
        "| Peak | Multiplicity | Integral | Candidate assignments | Status |",
        "|---|---:|---:|---|---|",
    ]
    for assignment in assignments:
        candidates = _format_candidates(assignment.candidates)
        lines.append(
            "| "
            f"{_format_peak(assignment.peak)} | "
            f"{assignment.peak.multiplicity or ''} | "
            f"{_format_optional_number(assignment.peak.integration)} | "
            f"{candidates} | "
            f"{assignment.status} |"
        )
    return lines


def _format_candidates(candidates: tuple[AssignmentCandidate, ...]) -> str:
    if not candidates:
        return "needs review"
    rendered: list[str] = []
    for candidate in candidates[:3]:
        evidence = "; ".join(candidate.evidence)
        rendered.append(f"{candidate.label} ({candidate.confidence:.2f}; {evidence})")
    return "<br>".join(rendered)


def _render_warning_lines(warnings: tuple[AssignmentWarning, ...]) -> list[str]:
    if not warnings:
        return ["- No warnings."]
    return [f"- **{warning.severity} / {warning.code}**: {warning.message}" for warning in warnings]


def _format_peak(peak: NMRPeak) -> str:
    if peak.shift_range is None:
        return f"δ {peak.shift_ppm:.2f}"
    low, high = peak.shift_range
    return f"δ {high:.2f}–{low:.2f}"


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return ""
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")
