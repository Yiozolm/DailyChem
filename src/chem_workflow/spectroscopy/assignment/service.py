"""Generate conservative rule-based NMR assignment candidates and warnings."""

from __future__ import annotations

from rdkit import Chem

from chem_workflow.compounds.structure import mol_info
from chem_workflow.spectroscopy.assignment.features import (
    detect_carbon_features,
    detect_proton_features,
)
from chem_workflow.spectroscopy.assignment.models import (
    AssignmentCandidate,
    AssignmentDraft,
    AssignmentError,
    AssignmentRule,
    AssignmentStatus,
    AssignmentWarning,
    DetectedFeature,
    PeakAssignment,
    WarningSeverity,
)
from chem_workflow.spectroscopy.assignment.rendering import (
    _format_optional_number,
    _format_peak,
)
from chem_workflow.spectroscopy.assignment.rules import (
    DEFAULT_13C_RULES_PATH,
    load_assignment_rules,
)
from chem_workflow.spectroscopy.nmr.consistency import check_signal_count
from chem_workflow.spectroscopy.nmr.models import NMRPeak, NMRSpectrum
from chem_workflow.spectroscopy.nmr.parsing import normalize_multiplicity


def assign_1h_nmr(
    mol: Chem.Mol,
    spectrum: NMRSpectrum,
    *,
    rules: list[AssignmentRule] | None = None,
) -> AssignmentDraft:
    """Generate a candidate 1H assignment draft (thin wrapper over :func:`assign_nmr`)."""
    if spectrum.nucleus != "1H":
        raise AssignmentError("assign_1h_nmr 只支持 1H NMR；其它核种请用 assign_nmr。")
    return assign_nmr(mol, spectrum, rules=rules)

def assign_nmr(
    mol: Chem.Mol,
    spectrum: NMRSpectrum,
    *,
    rules: list[AssignmentRule] | None = None,
) -> AssignmentDraft:
    """Generate a candidate assignment draft for a 1H or 13C NMR spectrum."""
    if spectrum.nucleus not in ("1H", "13C"):
        raise AssignmentError(
            f"当前 assignment assistant 只支持 1H / 13C；收到 {spectrum.nucleus}。"
        )
    if not spectrum.peaks:
        raise AssignmentError("NMR spectrum 没有 peak，无法生成 assignment 草稿。")

    is_carbon = spectrum.nucleus == "13C"
    if rules is not None:
        assignment_rules = rules
    elif is_carbon:
        assignment_rules = load_assignment_rules(default_path=DEFAULT_13C_RULES_PATH)
    else:
        assignment_rules = load_assignment_rules()

    info = mol_info(mol)
    features = detect_carbon_features(mol) if is_carbon else detect_proton_features(mol)
    peak_assignments = tuple(
        _assign_peak(peak, assignment_rules, features) for peak in spectrum.peaks
    )
    expected_protons = _expected_proton_count(mol)
    warnings = _build_warnings(
        spectrum=spectrum,
        mol=mol,
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
        nucleus=spectrum.nucleus,
    )

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
    mol: Chem.Mol,
    expected_protons: int,
    features: tuple[DetectedFeature, ...],
    rules: list[AssignmentRule],
    peak_assignments: tuple[PeakAssignment, ...],
) -> tuple[AssignmentWarning, ...]:
    warnings: list[AssignmentWarning] = []
    warnings.extend(_signal_count_warnings(mol, spectrum))
    if spectrum.nucleus == "1H":
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

def _signal_count_warnings(
    mol: Chem.Mol,
    spectrum: NMRSpectrum,
) -> list[AssignmentWarning]:
    check = check_signal_count(mol, spectrum)
    if check.verdict == "match":
        return [
            AssignmentWarning(
                code="signal_count_match",
                message=check.message,
                severity="info",
            )
        ]
    severity: WarningSeverity = "risk" if check.verdict == "more_observed" else "warning"
    return [
        AssignmentWarning(
            code="signal_count_mismatch",
            message=check.message,
            severity=severity,
        )
    ]

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

def _expected_proton_count(mol: Chem.Mol) -> int:
    with_h = Chem.AddHs(mol)
    return sum(1 for atom in with_h.GetAtoms() if atom.GetAtomicNum() == 1)

__all__ = ["assign_1h_nmr", "assign_nmr"]

