"""Detect supported proton and carbon structural features with RDKit."""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import rdchem

from chem_workflow.spectroscopy.assignment.models import DetectedFeature


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

def detect_carbon_features(mol: Chem.Mol) -> tuple[DetectedFeature, ...]:
    """Detect common carbon-type structural features for 13C assignment."""
    features: list[DetectedFeature] = []
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6:
            continue
        feature = _classify_carbon(atom)
        if feature is not None:
            features.append(feature)
    return tuple(_dedupe_features(features))

def _classify_carbon(atom: Chem.Atom) -> DetectedFeature | None:
    idx = atom.GetIdx()
    neighbors = list(atom.GetNeighbors())
    has_double_o = any(_is_double_bond_to_oxygen(bond, atom) for bond in atom.GetBonds())
    has_triple_n = any(
        bond.GetBondType() == rdchem.BondType.TRIPLE
        and bond.GetOtherAtom(atom).GetAtomicNum() == 7
        for bond in atom.GetBonds()
    )
    has_triple_c = any(
        bond.GetBondType() == rdchem.BondType.TRIPLE
        and bond.GetOtherAtom(atom).GetAtomicNum() == 6
        for bond in atom.GetBonds()
    )
    has_double_c = any(
        bond.GetBondType() == rdchem.BondType.DOUBLE
        and bond.GetOtherAtom(atom).GetAtomicNum() == 6
        for bond in atom.GetBonds()
    )

    if has_double_o:
        return _carbon_feature("carbonyl_C", "carbonyl / carboxyl C", idx)
    if has_triple_n:
        return _carbon_feature("nitrile_C", "nitrile C", idx)
    if atom.GetIsAromatic():
        return _carbon_feature("aromatic_C", "aromatic C", idx)
    if has_triple_c:
        return _carbon_feature("alkyne_C", "alkyne C", idx)
    if has_double_c:
        return _carbon_feature("alkene_C", "alkene C", idx)
    if any(neighbor.GetAtomicNum() == 8 for neighbor in neighbors):
        return _carbon_feature("O_C", "O-bound C (OCH3 / OCH2 / OCH)", idx)
    if any(neighbor.GetAtomicNum() == 7 for neighbor in neighbors):
        return _carbon_feature("N_C", "N-bound C", idx)
    return _carbon_feature("aliphatic_C", "aliphatic C", idx)

def _carbon_feature(feature_id: str, label: str, idx: int) -> DetectedFeature:
    return DetectedFeature(
        feature_id=feature_id,
        label=label,
        description=label,
        atom_indices=(idx,),
    )

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

__all__ = ["detect_carbon_features", "detect_proton_features"]

