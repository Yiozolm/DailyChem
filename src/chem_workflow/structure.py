"""化合物结构输入与标准化。

支持的输入格式：
- SMILES 字符串
- `.smi` / `.smiles` 文本文件（取首行非空非注释）
- `.mol` MDL Molfile
- `.sdf` SDFile（取首个分子）
- `.cdx` ChemDraw 二进制（依赖 rdkit 的 ChemDraw 扩展，PyPI 轮子已内置）
- `.cdxml` ChemDraw XML
"""

from __future__ import annotations

import warnings
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors
from rdkit.Chem.Draw import rdMolDraw2D

_CDX_SUFFIXES = {".cdx", ".cdxml"}
_MOL_SUFFIXES = {".mol", ".sdf"}
_SMILES_SUFFIXES = {".smi", ".smiles"}
_IMAGE_SUFFIXES = {".svg", ".png"}
SUPPORTED_SUFFIXES = _CDX_SUFFIXES | _MOL_SUFFIXES | _SMILES_SUFFIXES


class StructureInputError(ValueError):
    """结构输入解析失败时抛出。错误信息会展示给用户，应包含可操作建议。"""


def parse_smiles(smiles: str) -> Chem.Mol:
    """校验并解析 SMILES 字符串。

    返回 RDKit `Mol`；非法 SMILES 抛 `StructureInputError`。
    """
    if not smiles or not smiles.strip():
        raise StructureInputError("SMILES 为空")
    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        raise StructureInputError(f"非法 SMILES：{smiles!r}")
    return mol


def _load_cdx(path: Path) -> Chem.Mol:
    if not Chem.HasChemDrawCDXSupport():
        raise StructureInputError(
            f"当前 RDKit 构建不支持 {path.suffix}。"
            f"请在 ChemDraw 中将 {path.name} 另存为 .mol 或 .sdf 后重试。"
        )
    mols = Chem.MolsFromCDXMLFile(str(path))  # Auto 自动嗅探 .cdx vs .cdxml
    if not mols:
        raise StructureInputError(f"{path.name}: ChemDraw 文件解析为空")
    if len(mols) > 1:
        warnings.warn(
            f"{path.name}: 期望单一化合物，实际解析出 {len(mols)} 个；取第一个。"
            f" 如果是合成路线 / 多分子文件，请单独导出目标分子。",
            stacklevel=2,
        )
    return mols[0]


def _load_mol_or_sdf(path: Path) -> Chem.Mol:
    if path.suffix.lower() == ".sdf":
        supplier = Chem.SDMolSupplier(str(path))
        mols = [m for m in supplier if m is not None]
        if not mols:
            raise StructureInputError(f"{path.name}: SDF 中没有可解析的分子")
        if len(mols) > 1:
            warnings.warn(
                f"{path.name}: SDF 含 {len(mols)} 个分子，取第一个。",
                stacklevel=2,
            )
        return mols[0]
    mol = Chem.MolFromMolFile(str(path))
    if mol is None:
        raise StructureInputError(f"{path.name}: MOL 文件解析失败")
    return mol


def _load_smiles_file(path: Path) -> Chem.Mol:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            # SMILES 文件可能是 "SMILES<TAB>name"，取第一列
            return parse_smiles(stripped.split()[0])
    raise StructureInputError(f"{path.name}: SMILES 文件无有效内容")


def load_structure(path: str | Path) -> Chem.Mol:
    """根据后缀自动分派到对应的解析器。

    抛 `StructureInputError`：文件不存在 / 后缀不支持 / 解析失败。
    """
    path = Path(path)
    if not path.exists():
        raise StructureInputError(f"文件不存在：{path}")
    suffix = path.suffix.lower()
    if suffix in _CDX_SUFFIXES:
        return _load_cdx(path)
    if suffix in _MOL_SUFFIXES:
        return _load_mol_or_sdf(path)
    if suffix in _SMILES_SUFFIXES:
        return _load_smiles_file(path)
    raise StructureInputError(
        f"未识别的结构文件类型：{suffix or '(无后缀)'}。"
        f" 支持的格式：{sorted(SUPPORTED_SUFFIXES)} 或直接传 SMILES 字符串。"
    )


def mol_info(mol: Chem.Mol) -> dict[str, object]:
    """返回分子基本信息字典：canonical SMILES、分子式、分子量、原子数。"""
    if mol is None:
        raise StructureInputError("mol 为 None")
    return {
        "smiles": Chem.MolToSmiles(mol),
        "formula": AllChem.CalcMolFormula(mol),
        "mol_weight": round(Descriptors.MolWt(mol), 3),
        "heavy_atoms": mol.GetNumHeavyAtoms(),
        "num_atoms": mol.GetNumAtoms(),
    }


def draw_structure(
    mol: Chem.Mol,
    out_path: str | Path,
    *,
    show_atom_index: bool = False,
    size: tuple[int, int] = (500, 500),
) -> Path:
    """把分子渲染为 SVG / PNG，按 `out_path` 后缀分派。

    返回写入的 Path。`show_atom_index=True` 时叠加 RDKit 0-based 原子编号
    （Phase 8 assignment 辅助会用到）。
    """
    if mol is None:
        raise StructureInputError("mol 为 None")
    out = Path(out_path)
    suffix = out.suffix.lower()
    if suffix not in _IMAGE_SUFFIXES:
        raise StructureInputError(
            f"未识别的图片格式：{suffix or '(无后缀)'}。 支持：{sorted(_IMAGE_SUFFIXES)}"
        )

    width, height = size
    if suffix == ".svg":
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    else:  # .png
        drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
    drawer.drawOptions().addAtomIndices = show_atom_index
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()

    out.parent.mkdir(parents=True, exist_ok=True)
    data = drawer.GetDrawingText()
    if suffix == ".svg":
        out.write_text(data, encoding="utf-8")
    else:
        out.write_bytes(data)
    return out
