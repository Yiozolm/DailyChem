"""Phase 8 enhancement: theoretical signal-count consistency check.

A lightweight stand-in for "predicted vs observed spectrum" comparison (the chemist's
"对得上就OK，对不上就错"). It does NOT predict chemical-shift *values*; it counts how many
*unique* signals a structure should show for a nucleus (via RDKit symmetry classes) and compares
that to the number of observed peaks, flagging over/under counts for manual review.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from rdkit import Chem

from chem_workflow.spectroscopy.nmr.models import NMRSpectrum

_ELEMENT_FOR_NUCLEUS = {"13C": "C", "19F": "F", "31P": "P"}
SignalVerdict = Literal["match", "fewer_observed", "more_observed"]


class ConsistencyError(ValueError):
    """信号数一致性检查失败时抛出。错误信息会展示给用户，应包含可操作建议。"""


class SignalCountCheck(BaseModel):
    """Result of comparing structure-derived unique signals against observed peaks."""

    nucleus: str
    expected_unique_signals: int
    observed_peaks: int
    verdict: SignalVerdict
    message: str


def expected_unique_signals(mol: Chem.Mol, nucleus: str) -> int:
    """Count symmetry-unique signals a structure should show for ``nucleus``.

    Uses RDKit canonical ranks (without tie-breaking) so symmetry-equivalent atoms share a rank.
    For 1H, counts unique environments among hydrogen atoms; for 13C/19F/31P, among C/F/P atoms.
    """
    if mol is None:
        raise ConsistencyError("mol 为 None，无法计算理论信号数。")
    mol_h = Chem.AddHs(mol)
    ranks = list(Chem.CanonicalRankAtoms(mol_h, breakTies=False))

    if nucleus == "1H":
        target_atomic_num = 1
    else:
        element = _ELEMENT_FOR_NUCLEUS.get(nucleus)
        if element is None:
            raise ConsistencyError(
                f"暂不支持核种 {nucleus!r} 的信号数检查；支持 1H / 13C / 19F / 31P。"
            )
        target_atomic_num = Chem.GetPeriodicTable().GetAtomicNumber(element)

    unique = {
        ranks[atom.GetIdx()]
        for atom in mol_h.GetAtoms()
        if atom.GetAtomicNum() == target_atomic_num
    }
    return len(unique)


def check_signal_count(mol: Chem.Mol, spectrum: NMRSpectrum) -> SignalCountCheck:
    """Compare structure-derived unique signals against the observed peak count."""
    if not spectrum.peaks:
        raise ConsistencyError("NMR spectrum 没有 peak，无法做信号数检查。")
    expected = expected_unique_signals(mol, spectrum.nucleus)
    observed = len(spectrum.peaks)
    verdict, message = _verdict(spectrum.nucleus, expected, observed)
    return SignalCountCheck(
        nucleus=spectrum.nucleus,
        expected_unique_signals=expected,
        observed_peaks=observed,
        verdict=verdict,
        message=message,
    )


def _verdict(nucleus: str, expected: int, observed: int) -> tuple[SignalVerdict, str]:
    if observed == expected:
        return (
            "match",
            f"{nucleus}: 实测峰数 {observed} 与结构理论唯一信号数 {expected} 一致。",
        )
    if observed > expected:
        return (
            "more_observed",
            (
                f"{nucleus}: 实测峰数 {observed} 多于结构理论唯一信号数 {expected}；"
                "可能存在杂质峰、溶剂峰、旋转异构体/非对映异构，或结构对称性低于预期。"
            ),
        )
    return (
        "fewer_observed",
        (
            f"{nucleus}: 实测峰数 {observed} 少于结构理论唯一信号数 {expected}；"
            "可能存在信号重叠、偶然等价或漏峰。"
        ),
    )
