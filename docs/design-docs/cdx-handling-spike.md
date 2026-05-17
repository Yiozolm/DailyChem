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

## 实战验证（2026-05-17）

拿到了同学提供的两份脱敏 `.cdx` 在本机（macOS arm64 / Python 3.13.5 / rdkit 2026.3.1）跑过。

### 用例 1：多分子合成路线 `data/raw/synthesis route(cys).cdx`（50 KB）

`Chem.MolsFromCDXMLFile` 默认 `Auto` 模式直接解析二进制 `.cdx`，返回 31 个 `Mol`。

按"heavy_atoms ≥ 3 且 SMILES 不含 `*`"过滤后剩 13 个，覆盖：

- BTD 芳杂环骨架的溴化 / 硝化 / 氨基化 / 噻吩 cross-coupling 中间体
- Pd-coupling 试剂（pinacol boronate、Stille 试剂）
- 季铵正离子（电荷保留）
- 最终丙烯酸酯单体（51 重原子，MW 733）

观察到的告警（不致命）：

- `Unhandled generic nickname: G` × 2 —— ChemDraw 里有 `G` 通用基团标签，RDKit 不识别
- `Incomplete atom labelling, cannot make bond` × 7 —— 因为上一项导致的局部键缺失

被过滤掉的 18 项主要是：单原子标签（B/C/F/H/Fe/I）、试剂注释带 `*` 通配（HNO₃、AcOH、NaNO₂、TfOH、Pd(PPh₃)₄、`Y-I`）。
**注意**：试剂/溶剂注释虽然被简单过滤剔除，但化学家在实验记录里是要这些信息的；合成路线模式（后续 P1）需要更聪明的分类策略，单化合物模式 MVP 不受影响。

### 用例 2：单化合物 `data/raw/1.cdx`（3 KB）

合成路线里的 compound B（同学的命名）单独存为 `.cdx` 后：

- `MolsFromCDXMLFile` 返回**正好 1 个** `Mol`
- canonical SMILES、分子式（C₆Br₂N₄O₄S）、MW（383.96）与合成路线解析结果完全一致 → 单分子和多分子两条路径给出同一个 canonical SMILES，**结果可重现**
- 无 warning，无 incomplete labelling

### 用例 3：跨格式一致性 `compound_b_single.{cdx,cdxml,mol,sdf}`（2026-05-17 补充）

同学补提供了 compound B 的 ChemDraw v20 三种导出格式（`.cdxml` / `.mol` / `.sdf`，**ChemDraw v20 的 File→Save As 菜单里没有 `.smi`**）。

| 格式 | canonical SMILES | 分子式 | MW |
|---|---|---|---|
| `.cdx`   | `O=[N+]([O-])c1c([N+](=O)[O-])c(Br)c2nsnc2c1Br` | `C6Br2N4O4S` | 383.96 |
| `.cdxml` | 同上 | 同上 | 同上 |
| `.mol`   | 同上 | 同上 | 同上 |
| `.sdf`   | 同上 | 同上 | 同上 |

**结论**：4 种格式经 RDKit 解析后给出完全一致的 canonical SMILES / 分子式 / 分子量。MVP 接受任一格式都安全，用户可以用 ChemDraw 最顺手的导出方式。已加 `test_load_structure_cross_format_consistency` 参数化测试做长期保护。

### 结论

- 方案 A（RDKit 原生 CDX）在真实多分子合成路线和单化合物两个用例上均验证通过。
- 单化合物 MVP 路径直接走 `mols = MolsFromCDXMLFile(path); mols[0]`；当 `len(mols) > 1` 时给出警告并取首个。
- 多分子 / 合成路线模式列入 Phase 2 之后的扩展。

## 待办：用真实样例验证

调研结束后，几件必须用真实文件验证的事：

- [x] 拿 1 个真实 v20 导出 `.cdx`，跑 `Chem.MolsFromCDXMLFile`，验证：
  - [x] 能解析出 `Mol`
  - [x] canonical SMILES 与 v20 其他导出格式（.cdxml/.mol/.sdf）一致；ChemDraw v20 菜单里**无 `.smi` 选项**，对照 `.smi` 不再追
  - [x] 分子式、分子量与其他格式一致（跨格式对照见用例 3）
  - ~~立体化学（手性、E/Z）是否保留~~ **不做**：同学反馈当前项目用不到含手性中心的化合物；如果后续遇到再补验证。
- [x] 同一个化合物分别用 v20 导出 `.cdx`、`.cdxml`、`.mol`、`.sdf` 四种格式（v20 的 Save As 菜单无 `.smi` 选项），确认四种路径给出同一 canonical SMILES（见用例 3）。
- [x] 试一个包含反应箭头/多分子的 `.cdx`，确认 RDKit 返回多个 `Mol`，且我们的"取首个"策略是否合理 → 结论：单化合物模式取首个 OK；合成路线模式需要后续设计分类策略
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
