"""Phase 2.1 单化合物结构输入测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem

from chem_workflow.structure import (
    StructureInputError,
    load_structure,
    mol_info,
    parse_smiles,
)

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "raw"
COMPOUND_B_CDX = FIXTURES / "compound_b_single.cdx"
SYNTHESIS_ROUTE_CDX = FIXTURES / "synthesis_route_cys.cdx"

# 来自 docs/design-docs/cdx-handling-spike.md 的预期值
COMPOUND_B_SMILES = "O=[N+]([O-])c1c([N+](=O)[O-])c(Br)c2nsnc2c1Br"
COMPOUND_B_FORMULA = "C6Br2N4O4S"
COMPOUND_B_MW = 383.96


def test_parse_smiles_returns_canonical_mol():
    mol = parse_smiles("CCO")
    assert mol is not None
    assert Chem.MolToSmiles(mol) == "CCO"


def test_parse_smiles_rejects_garbage():
    with pytest.raises(StructureInputError, match="非法 SMILES"):
        parse_smiles("not-a-valid-smiles$$$")


def test_parse_smiles_rejects_empty():
    with pytest.raises(StructureInputError, match="SMILES 为空"):
        parse_smiles("   ")


def test_load_structure_cdx_single_compound():
    """compound_b_single.cdx 是单化合物，应返回 1 个 Mol 不带警告。"""
    mol = load_structure(COMPOUND_B_CDX)
    info = mol_info(mol)
    assert info["smiles"] == COMPOUND_B_SMILES
    assert info["formula"] == COMPOUND_B_FORMULA
    assert info["mol_weight"] == pytest.approx(COMPOUND_B_MW, abs=0.01)
    assert info["heavy_atoms"] == 17


def test_load_structure_cdx_multi_compound_warns():
    """synthesis_route_cys.cdx 含 31 个 Mol，应给出警告并取首个。"""
    with pytest.warns(UserWarning, match="期望单一化合物"):
        mol = load_structure(SYNTHESIS_ROUTE_CDX)
    info = mol_info(mol)
    # 合成路线第一个分子在 spike 文档里记录为 C6Br2N4O4S，与 compound B 同结构
    assert info["formula"] == COMPOUND_B_FORMULA


def test_load_structure_unknown_suffix(tmp_path):
    p = tmp_path / "foo.xyz"
    p.write_text("garbage")
    with pytest.raises(StructureInputError, match="未识别的结构文件类型"):
        load_structure(p)


def test_load_structure_missing_file(tmp_path):
    with pytest.raises(StructureInputError, match="文件不存在"):
        load_structure(tmp_path / "nope.cdx")


def test_load_structure_smi_file(tmp_path):
    p = tmp_path / "test.smi"
    p.write_text("# comment line\n\nCCO ethanol\n")
    mol = load_structure(p)
    assert Chem.MolToSmiles(mol) == "CCO"


def test_load_structure_mol_file(tmp_path):
    """用 RDKit 写出一个 .mol，再读回来。"""
    mol_in = parse_smiles("CCO")
    p = tmp_path / "ethanol.mol"
    p.write_text(Chem.MolToMolBlock(mol_in))
    mol_out = load_structure(p)
    assert Chem.MolToSmiles(mol_out) == "CCO"


def test_load_structure_sdf_file(tmp_path):
    mol_in = parse_smiles("CCO")
    p = tmp_path / "ethanol.sdf"
    # SDF 是 MolBlock 加 $$$$ 结尾
    p.write_text(Chem.MolToMolBlock(mol_in) + "$$$$\n")
    mol_out = load_structure(p)
    assert Chem.MolToSmiles(mol_out) == "CCO"


def test_mol_info_keys():
    mol = parse_smiles("c1ccccc1")
    info = mol_info(mol)
    assert set(info.keys()) == {
        "smiles",
        "formula",
        "mol_weight",
        "heavy_atoms",
        "num_atoms",
    }
    assert info["formula"] == "C6H6"
    assert info["heavy_atoms"] == 6
