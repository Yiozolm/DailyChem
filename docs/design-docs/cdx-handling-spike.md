# `.cdx` 处理调研笔记（CDX Handling Spike）

> 目的：回答 `docs/exec-plans/active/chem_ai_workflow_todo.md` Phase 2 "输入格式约定"里
> 三选一决策的依据，并确定 MVP 走哪条路径。
> 调研日期：2026-05-17。本项目环境：macOS arm64，Python 3.13.5，rdkit 2026.3.1。

## TL;DR（结论先行）

- **当前 RDKit 2026.3.1（PyPI 默认轮子）已经原生支持读取 `.cdx` 和 `.cdxml`**。`Chem.HasChemDrawCDXSupport()` 在我们项目的虚拟环境里返回 `True`。
- **推荐方案**：以 RDKit 原生 `MolsFromCDXMLFile`（参数 `CDXMLFormat::Auto`）为主路径，自动识别二进制 `.cdx` 与 XML `.cdxml`；引导用户从 ChemDraw v20 导出 `.mol`/`.sdf`/SMILES 作为**兜底错误提示**而非强制要求。
- **不引入 OpenBabel 依赖**：避开二进制依赖、Apple Silicon 兼容性、Python 绑定不稳定（`obabel` CLI 在 `.cdx` 上有过崩溃记录）等问题。
- **不引入 pycdxml 作为强依赖**，但保留它作为"RDKit 解析失败时降级"的可选 fallback。

## 背景

化学同学日常用 ChemDraw v20，主要交付的结构文件是二进制 `.cdx`。
MVP 不能假设用户会主动导出 `.mol`/`.sdf`/SMILES — Phase 0 反馈里明确要求 `.cdx` 也能进入工作流。

`.cdx` 是 ChemDraw 的二进制 tagged 格式；`.cdxml` 是其等价 XML 表达。
两者的官方规范来自 Revvity（前 PerkinElmer / CambridgeSoft），公开但比较老。

## 候选方案对比

### 方案 A：RDKit 原生 CDX 解析【推荐】

**事实验证（本项目环境）：**

```python
>>> from rdkit import Chem
>>> Chem.HasChemDrawCDXSupport()
True
>>> list(Chem.CDXMLFormat.names)
['CDXML', 'CDX', 'Auto']
>>> p = Chem.CDXMLParserParams()
>>> p.format            # 默认 Auto
>>> Chem.MolsFromCDXMLFile.__doc__
# "If the ChemDraw extensions are available,
#  CDXMLFormat::Auto attempts to see if the input string is CDXML or CDX"
```

也就是说：

- 用 `Chem.MolsFromCDXMLFile(path)` + 默认 `CDXMLFormat.Auto`，RDKit 会自动嗅探 `.cdx` 还是 `.cdxml`，统一解析为 `Mol` 对象的列表。
- 由 Revvity ChemDraw parser 提供，已编译进 PyPI 的 rdkit 轮子（至少 2026.3.1 + 我们这台 Python 3.13 / macOS arm64 是包含的）。
- RDKit 官方说明：CDXML 格式很大很复杂，**只支持分子和反应解析的基础功能**，2D 布局、反应箭头注释、文字框等元数据会丢。对我们 MVP（只需要 SMILES + 基本元数据）完全够用。

**优点**

- 零新增依赖：rdkit 已经是项目核心包。
- 跨平台：PyPI 轮子在 macOS / Linux / Windows 都带这个能力（需要每个目标平台再确认一次，但官方轮子应一致）。
- 直接得到 `Mol` 对象，下游 canonical SMILES / 分子式 / 分子量 / 结构图全都能复用 RDKit 现有管线。

**风险**

- 不是所有 RDKit 构建都包含此扩展（官方文档措辞是 "optional"）。需要在启动时检查 `HasChemDrawCDXSupport()` 并对结果做明确报错。
- 老旧 `.cdx`（ChemDraw 7 时代前）可能不符合现行规范，可能解析失败 — 用户用 v20，应不在此范围。
- 复杂结构（有机金属、聚合物、Markush）解析结果不保证 — MVP 用例是常规小分子，可接受。

### 方案 B：pycdxml（纯 Python 备选）

[`kienerj/pycdxml`](https://github.com/kienerj/pycdxml) 是社区维护的纯 Python `.cdx` ↔ `.cdxml` 转换工具。

**优点**

- 纯 Python，不需要 ChemDraw 安装，跨平台。
- 思路是先把 `.cdx` 转成 `.cdxml`，因为 XML 操作比二进制简单。

**缺点**

- 仓库自述为 "experimental"，无稳定 release，GPLv3 协议（与我们项目兼容性需评估，但 MVP 不发布也无所谓）。
- 已知问题：ChemDraw 7 时代以前的 `.cdx` 经常解析失败；复杂分子（有机金属、聚合物）易失败。
- 多一层中间格式转换，调试链更长。

**定位**：作为方案 A 失败时的降级路径（捕获 RDKit 异常 → 用 pycdxml 转 `.cdxml` → 再喂回 RDKit 解析）。**不进 MVP**，列为后续 P2 改进。

### 方案 C：OpenBabel via `obabel` CLI

历史上 ChemDraw → MOL 转换的"默认答案"。

**优点**

- 支持广泛，命令一行：`obabel -i cdx in.cdx -o sdf > out.sdf`。
- 文档成熟，社区案例多。

**缺点**

- 引入 **C++ 二进制依赖**，需要用户安装 `openbabel`（Homebrew/apt/conda），跨平台分发会变复杂 — 与"面向非程序员化学同学"目标冲突。
- OpenBabel 的 Python 绑定（`pybel`）对 `.cdx` 历史上有崩溃记录（[openbabel/openbabel#1690](https://github.com/openbabel/openbabel/issues/1690)），所以即使依赖了也只能 subprocess 调 `obabel` 二进制。
- `.cdx` 在 OpenBabel 文档里标为 "read-only" + "minimal support of chemical structure information only" — 信息保真度并不优于 RDKit。
- 反应信息丢失风险与 RDKit 类似（"impedance mismatch between CDX and molfile"）。

**定位**：不进 MVP。如果方案 A、B 都不可用，再考虑用 OpenBabel 兜底。

### 方案 D：纯文档引导（保守路线）

CLI 不接受 `.cdx`，文档/错误提示告诉用户在 ChemDraw v20 里 `File → Save As → MDL Molfile/SDFile`。

**优点**

- 零技术负担，工作量最小。

**缺点**

- 与 Phase 0 验收冲突 — 同学的痛点正是"用 `.cdx` 不方便"。
- 用户体验差：每个化合物多一次手动导出操作，与"减少琐事"的项目目标相反。

**定位**：作为方案 A 不可用时的**最终兜底**（在 `HasChemDrawCDXSupport()` 为 False 的奇怪环境里，错误信息里就引导手动导出）。

## 推荐实施路径（MVP）

```python
# src/chem_workflow/structure.py（伪代码）

from pathlib import Path
from rdkit import Chem


def load_structure(path: Path) -> Chem.Mol:
    suffix = path.suffix.lower()

    if suffix in {".mol", ".sdf"}:
        return Chem.MolFromMolFile(str(path))

    if suffix in {".cdx", ".cdxml"}:
        if not Chem.HasChemDrawCDXSupport():
            raise StructureInputError(
                f"当前 RDKit 构建不支持 .cdx/.cdxml。"
                f"请在 ChemDraw v20 中将 {path.name} 另存为 .mol 或 .sdf 后重试。"
            )
        mols = Chem.MolsFromCDXMLFile(str(path))  # Auto 自动识别 cdx vs cdxml
        if not mols:
            raise StructureInputError(f"{path.name} 解析为空，请检查文件")
        return mols[0]  # MVP：第一版只取首个分子

    if suffix in {".smi", ".smiles"} or "smiles" in path.read_text()[:200]:
        ...  # SMILES 路径

    raise StructureInputError(f"未识别的结构文件类型：{suffix}")
```

要点：

1. 启动时检查 `Chem.HasChemDrawCDXSupport()`，结果写进诊断日志。
2. `.cdx` 和 `.cdxml` 走同一函数 `MolsFromCDXMLFile`（默认 Auto）。
3. 失败时错误信息直接告诉用户怎么导出，避免卡住。
4. MVP 先支持"一个 `.cdx` 文件一个目标分子"，多分子 `.cdx` 留到后续。

## 待办：用真实样例验证

调研结束后，还有几件必须用真实文件验证的事，等同学提供脱敏 `.cdx` 后做：

- [ ] 拿 1 个真实 v20 导出 `.cdx`，跑 `Chem.MolsFromCDXMLFile`，验证：
  - [ ] 能解析出 `Mol`
  - [ ] canonical SMILES 与 ChemDraw "Save As SMILES" 输出一致
  - [ ] 分子式、分子量与 ChemDraw 标注一致
  - [ ] 立体化学（手性、E/Z）是否保留
- [ ] 同一个化合物分别用 v20 导出 `.cdx`、`.cdxml`、`.mol`、`.sdf`、`.smi`，确认五种路径给出同一个 canonical SMILES。
- [ ] 试一个包含反应箭头/多分子的 `.cdx`，确认 RDKit 返回多个 `Mol`，且我们的"取首个"策略是否合理（可能需要让用户指定 compound_id）。
- [ ] 在 Linux / Windows 上分别 `uv sync` 后跑 `Chem.HasChemDrawCDXSupport()`，确认跨平台一致返回 True（如果有某个平台 False，则需要更明显的安装文档）。

## 对 Phase 2 计划的影响

如果方案 A 在真实样例上验证通过，则 Phase 2 输入格式约定可以从"三选一未定"收敛为：

> 第一版 CLI 直接接受 `.cdx` / `.cdxml` / `.mol` / `.sdf` / SMILES；
> 解析统一由 RDKit 完成，不引入额外依赖。
> 启动检查 `HasChemDrawCDXSupport()`，不可用时退化为引导用户手动导出。

也即原计划的"方案 3（直接解析）"可以实现，且**无需额外依赖**。

## 参考资料

- RDKit 官方 - [`Chem.MolsFromCDXMLFile` API（实测 docstring）](https://www.rdkit.org/docs/cppapi/namespaceRDKit_1_1v2_1_1CDXMLParser.html)
- RDKit GitHub Discussion - [How to convert to CDXML? #4762](https://github.com/rdkit/rdkit/discussions/4762)
- pycdxml - [kienerj/pycdxml](https://github.com/kienerj/pycdxml)
- Open Babel - [ChemDraw binary format (cdx)](https://open-babel.readthedocs.io/en/latest/FileFormats/ChemDraw_binary_format.html)
- Open Babel issue - [System crash on converting `.cdx` files using Python interface #1690](https://github.com/openbabel/openbabel/issues/1690)
- Depth-First - [Reading and Translating ChemDraw CDX Files with OpenBabel](https://depth-first.com/articles/2010/09/17/reading-and-translating-chemdraw-cdx-files-with-openbabel/)
- Library of Congress - [ChemDraw Exchange (CDX) format profile](https://loc.gov/preservation/digital/formats/fdd/fdd000582.shtml)
