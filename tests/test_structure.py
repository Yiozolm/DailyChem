"""Phase 2.1 单化合物结构输入测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem

from chem_workflow.structure import (
    StructureInputError,
    draw_structure,
    load_structure,
    mol_info,
    parse_smiles,
)

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "raw"
COMPOUND_B_CDX = FIXTURES / "compound_b_single.cdx"
COMPOUND_B_CDXML = FIXTURES / "compound_b_single.cdxml"
COMPOUND_B_MOL = FIXTURES / "compound_b_single.mol"
COMPOUND_B_SDF = FIXTURES / "compound_b_single.sdf"
COMPOUND_B_SMI = FIXTURES / "compound_b_single.smi"
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


@pytest.mark.parametrize(
    "fixture",
    [COMPOUND_B_CDX, COMPOUND_B_CDXML, COMPOUND_B_MOL, COMPOUND_B_SDF, COMPOUND_B_SMI],
    ids=["cdx", "cdxml", "mol", "sdf", "smi"],
)
def test_load_structure_cross_format_consistency(fixture):
    """compound B 的 5 种 ChemDraw v20 导出格式应给出同一 canonical SMILES。

    SMILES 是同学从 ChemDraw v20 `Edit → Copy As → SMILES` 复制出来的
    Kekulé 形式，RDKit canonicalize 后应与其他 4 种格式一致。
    """
    info = mol_info(load_structure(fixture))
    assert info["smiles"] == COMPOUND_B_SMILES
    assert info["formula"] == COMPOUND_B_FORMULA
    assert info["mol_weight"] == pytest.approx(COMPOUND_B_MW, abs=0.01)


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


def test_draw_structure_svg(tmp_path):
    mol = parse_smiles("CCO")
    out = tmp_path / "ethanol.svg"
    written = draw_structure(mol, out)
    assert written == out and out.exists()
    content = out.read_text()
    assert content.startswith("<?xml")
    assert "<svg" in content and "</svg>" in content


def test_draw_structure_svg_with_atom_index(tmp_path):
    mol = parse_smiles("CCO")
    out_plain = tmp_path / "plain.svg"
    out_indexed = tmp_path / "indexed.svg"
    draw_structure(mol, out_plain, show_atom_index=False)
    draw_structure(mol, out_indexed, show_atom_index=True)
    # 带原子编号的 SVG 内容应更长（多了数字 text 元素）
    assert len(out_indexed.read_text()) > len(out_plain.read_text())


def test_draw_structure_png(tmp_path):
    mol = parse_smiles("CCO")
    out = tmp_path / "ethanol.png"
    draw_structure(mol, out)
    assert out.exists()
    # PNG 魔数
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_draw_structure_unknown_format(tmp_path):
    mol = parse_smiles("CCO")
    with pytest.raises(StructureInputError, match="未识别的图片格式"):
        draw_structure(mol, tmp_path / "out.gif")


def test_draw_structure_creates_parent_dir(tmp_path):
    mol = parse_smiles("CCO")
    out = tmp_path / "nested" / "dir" / "ethanol.svg"
    draw_structure(mol, out)
    assert out.exists()


def test_draw_structure_real_cdx(tmp_path):
    """端到端：从 .cdx 读结构，带 atom_index 渲染 SVG。"""
    mol = load_structure(COMPOUND_B_CDX)
    out = tmp_path / "compound_b.svg"
    draw_structure(mol, out, show_atom_index=True, size=(600, 600))
    content = out.read_text()
    assert "<svg" in content
    # heavy_atoms=17，atom index 0-16 至少有几个应在文本里
    assert ">0<" in content or "atom-0" in content or 'class="atom-0"' in content
