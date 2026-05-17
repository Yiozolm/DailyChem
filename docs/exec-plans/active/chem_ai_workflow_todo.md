# 化学工作流自动化项目 TODO List

## 项目目标

为化学专业同学构建一套轻量级编程/AI 辅助工具，用于加速以下工作流：

1. 化合物结构管理
2. 谱图数据整理
3. NMR peak list 标准化
4. 实验记录自动生成
5. 结构—谱图 assignment 辅助
6. 后续扩展到 MS / IR / UV / 文献检索

本项目不以“一步到位实现全自动 AI 解谱”为目标，而是优先实现稳定、可解释、可人工确认的半自动工具。

---

# Phase 0：需求澄清与样例数据收集

## 目标

弄清楚化学同学真实使用的数据格式、软件、命名习惯和实验记录格式。

## TODO

- [ ] 询问同学目前常用软件

  - [x] ChemDraw 版本：**v20**
  - [x] 用户常用结构文件格式：**ChemDraw `.cdx`**
  - [X] 是否使用 MestReNova / Mnova
  - [X] 是否使用 Bruker / JEOL / Agilent 仪器数据
  - [ ] 是否有电子实验记录本
  - [X] 是否主要用 Word / Excel / 手写 / Markdown 记录实验
- [ ] 收集 3–5 个真实但可脱敏的样例

  - [ ] 一个目标化合物结构文件：`.cdx` / `.mol` / `.sdf` / SMILES
  - [ ] 一份 1H NMR peak list
  - [ ] 一份 13C NMR peak list
  - [ ] 一份实验记录文本
  - [ ] 一份谱图 PDF 或图片
  - [ ] 一份最终论文/报告里的表征格式
- [ ] 明确第一版支持范围

  - [ ] 只支持 1H NMR
  - [X] 支持 1H + 13C NMR
  - [ ] 是否需要支持 19F / 31P
  - [X] 是否需要支持 MS / HRMS
  - [X] 是否需要英文实验记录
  - [ ] 是否需要中文实验记录

## 验收标准

- [ ] 至少拿到 3 个完整样例：结构 + NMR 数据 + 实验记录
- [x] 明确第一版输入/转换策略：
  - **结构**：`.cdx`（用户常用）/ `.cdxml` / `.mol` / `.sdf` / SMILES 全部接受；rdkit 2026.3.1 PyPI 轮子原生支持 `.cdx`/`.cdxml`，单化合物 MVP 已实现（见 `docs/design-docs/cdx-handling-spike.md`）。
  - **NMR**：接 **MestReNova 导出的 peak table（CSV 优先，文本报告备选）**。不接 Bruker 仪器原始数据目录（fid/acqus 等，等于重建 MestReNova），不接谱图截图（光栅图反推精度差且丢积分）。详见 `docs/design-docs/nmr-input-strategy.md`。
- [ ] 明确第一版输出格式
- [ ] 明确用户最常用的文件命名方式

## 可交付物

- [ ] `docs/requirements.md`
- [ ] `examples/raw/` 样例数据文件夹
- [ ] `examples/expected_outputs/` 期望输出文件夹

---

# Phase 1：项目骨架搭建

## 目标

搭建一个可持续迭代的小型 Python 项目。

## 推荐技术栈

- Python 3.11+
- RDKit：分子结构处理
- pandas：表格处理
- pydantic：数据结构校验
- typer：命令行工具
- streamlit：后续可视化界面
- pytest：测试
- SQLite：本地数据存储

## TODO

- [x] 创建项目结构

```text
chem-ai-workflow/
  README.md
  pyproject.toml
  .gitignore
  data/
    raw/
    processed/
  examples/
    raw/
    expected_outputs/
  docs/
    requirements.md
    workflow.md
  src/
    chem_workflow/
      __init__.py
      models.py
      structure.py
      nmr.py
      records.py
      storage.py
      cli.py
  tests/
    test_structure.py
    test_nmr.py
    test_records.py
```

- [x] 初始化 Git 仓库
- [x] 配置 Python 虚拟环境
- [x] 安装基础依赖
- [x] 配置代码格式化工具
  - [x] ruff
  - [x] black 或 ruff format
- [x] 配置 pytest
- [x] 写一个最小 CLI 命令

```bash
chemwf --help
```

## 验收标准

- [x] 项目可以本地安装
- [x] `pytest` 可以正常运行
- [x] `chemwf --help` 可以正常输出
- [x] README 中有安装和运行说明

## 可交付物

- [x] Git 仓库
- [x] 初始项目骨架
- [x] `README.md`

## 实施备注（2026-05-16）

- 项目放在 repo 根，不是子目录 `chem-ai-workflow/`；包名 `chem_workflow`，CLI 入口 `chemwf`。
- 包管理用 uv（按 `CLAUDE.md` 的约束），`uv sync` 自动建 `.venv`，`pyproject.toml` 用 `[dependency-groups].dev` 放 dev 依赖。
- ruff 同时承担 lint 和 format（`ruff check` + `ruff format`），未单独安装 black。
- `docs/` 已经按项目文档规范组织（`product-specs/`、`design-docs/`、`exec-plans/` 等），未生成原计划里的 `docs/requirements.md` / `docs/workflow.md`；后续 Phase 0 的 `requirements.md` 落到 `docs/product-specs/`。
- `tests/` 暂只放 `test_smoke.py`（验证 `__version__`），原计划的 `test_structure.py / test_nmr.py / test_records.py` 等到对应模块有实现再加。
- 实测：Python 3.13.5、rdkit 2026.3.1、pytest 9.0.3，`uv run chemwf version` 输出 `0.0.1`，`uv run ruff check .` 全绿。

---

# Phase 2：化合物结构输入与标准化

## 目标

支持用户常用的 ChemDraw `.cdx` 结构文件进入工作流，并支持用 SMILES / MOL / SDF 生成标准化分子信息。

## 输入格式约定

用户常用 ChemDraw v20 的 `.cdx`，因此第一版不能只假设用户会主动提供 `.mol` / `.sdf` / SMILES。

需要先做一个 CDX handling spike，确定 MVP 采用哪一种方案：

1. **保守方案**：CLI 仍只直接解析 `.mol` / `.sdf` / SMILES，但文档和错误提示清楚引导用户从 ChemDraw v20 导出这些格式。
2. **预处理方案**：增加 `.cdx → .mol` / `.sdf` 的转换步骤；可评估 OpenBabel 或 ChemDraw 导出的 CDXML/MOL 中间格式。
3. **直接解析方案**：CLI 直接接受 `.cdx`；需要确认二进制 `.cdx` 解析依赖、安装复杂度、结构信息保真度和跨平台稳定性。

当前技术判断：RDKit 原生不直接支持 ChemDraw 二进制 `.cdx`；如果要直接支持 `.cdx`，需要额外依赖或预处理工具。MVP 需要至少做到“遇到 `.cdx` 时给出明确、可操作的转换路径”，避免用户卡住。

## TODO

- [ ] 定义 compound 数据模型（**延后到 Phase 5**：实验记录开做时一起设计 schema 更准。当前 `mol_info()` 返回 dict 已够用。）

```python
class Compound:
    compound_id: str
    smiles: str
    molfile_path: str | None
    name: str | None
    formula: str | None
    molecular_weight: float | None
```

- [x] 实现 SMILES 读取

  - [x] 校验 SMILES 是否合法
  - [x] 生成 canonical SMILES
  - [x] 计算分子式
  - [x] 计算分子量
- [x] 实现 MOL / SDF 读取

  - [x] 从文件读取结构
  - [x] 转换为 canonical SMILES
  - [x] 提取分子基本信息
- [x] 评估并设计 `.cdx` 输入路径（结论见 `docs/design-docs/cdx-handling-spike.md`）

  - [x] 收集至少 1 个真实脱敏 `.cdx` 样例（合成路线 + 单化合物各一份）
  - [x] 验证 ChemDraw v20 导出 `.mol` / `.sdf` / `.cdxml` / `.smi` 是否保留关键结构信息：5 种格式给出同一 canonical SMILES / 分子式 / MW（`.smi` 在 v20 里走 Edit→Copy As→SMILES 剪贴板，不在 Save As 菜单；跨格式对照见 cdx-handling-spike.md 用例 3）
  - [x] 评估 OpenBabel 或 CDXML 中间格式作为 `.cdx` 预处理方案 → 不需要：rdkit 2026.3.1 PyPI 轮子已内置 ChemDraw 解析（`HasChemDrawCDXSupport() = True`）
  - [x] 决定 CLI 是否直接接受 `.cdx` → 是。直接走 `Chem.MolsFromCDXMLFile`（默认 Auto 嗅探 .cdx vs .cdxml）
  - [x] 单化合物 MVP 取首个 Mol；`len(mols) > 1` 时给警告但取首个；合成路线模式列入 Phase 2 之后的扩展
  - [ ] 如果某平台 `HasChemDrawCDXSupport()` 为 False，错误提示引导用户从 ChemDraw 手动导出 `.mol/.sdf`（保底）
- [x] 生成带原子编号的结构图

  - [x] 输出 SVG
  - [x] 输出 PNG
  - [x] 支持显示 atom index
- [x] 添加命令行接口

```bash
chemwf structure parse --smiles "CCOC(=O)c1ccccc1" --id C001
chemwf structure draw --smiles "CCOC(=O)c1ccccc1" --out C001.svg
```

## 验收标准

- [x] 输入合法 SMILES 时能输出 canonical SMILES、分子式、分子量
- [x] 输入非法 SMILES 时能给出清晰错误信息
- [x] 可以生成带 atom index 的结构图
- [x] 至少有 5 个结构相关单元测试（实际 17 个）

## 可交付物

- [x] `src/chem_workflow/structure.py`
- [x] `tests/test_structure.py`
- [x] `examples/processed/compound_structure.svg`

---

# Phase 3：NMR peak list 数据模型与解析

## 目标

把手动输入或 CSV 导出的 NMR peak list 转换为结构化数据。

## 第一版支持字段

```text
shift_ppm
integration
multiplicity
j_hz
assignment
note
```

## TODO

- [x] 定义 NMRPeak 数据模型

```python
class NMRPeak:
    shift_ppm: float | str
    integration: str | None
    multiplicity: str | None
    j_hz: list[float] | None
    assignment: str | None
    note: str | None
```

- [x] 定义 NMRSpectrum 数据模型

```python
class NMRSpectrum:
    nucleus: str
    frequency_mhz: int | None
    solvent: str | None
    peaks: list[NMRPeak]
```

- [x] 支持从 CSV 读取 peak list（**改为：MestReNova multiplet 表 tab-separated 文本**，决策见 `docs/design-docs/nmr-input-strategy.md` 现实校正小节）
- [x] 支持从手动文本读取简单 peak list（直接 `--inline` 贴 multiplet 表文本）
- [x] 标准化 multiplicity

  - [x] singlet → s
  - [x] doublet → d
  - [x] triplet → t
  - [x] quartet → q
  - [x] multiplet → m
  - [x] doublet of doublets → dd
- [x] 标准化 J coupling

  - [x] `8.0` → `[8.0]`
  - [x] `8.0, 2.0` → `[8.0, 2.0]`
  - [x] `J = 8.0 Hz` → `[8.0]`
- [x] 支持常见错误提示

  - [x] shift 缺失
  - [x] integration 缺失（缺时整峰 integration=None，下游 Phase 4 决定如何处理）
  - [x] multiplicity 不合法（warn 但保留原值）
  - [x] J 值格式错误（parser 容错：抓不到数字时返回空列表）

## 验收标准

- [x] 能读取至少 3 种不同格式的 peak list（multiplet 表文件 / `--inline` 文本 / case-insensitive 列名 / 短行自动 pad —— 共 4 种解析路径）
- [x] 能把 peak list 转成统一 JSON（`examples/processed/nmr_peaks.json`）
- [x] 错误输入有明确提示（缺 Shift 列 / Shift 非数值 / 表格非 Tab 分隔 / 空数据行 / 未知 multiplicity 警告）
- [x] 至少有 10 个 NMR parsing 单元测试（实际 34 个）

## 可交付物

- [x] `src/chem_workflow/nmr.py`
- [x] `tests/test_nmr.py`
- [x] `examples/processed/nmr_peaks.json`

## 实施备注（2026-05-17）

- 输入格式从原设计的"MestReNova Save As → Peak List CSV"调整为"View → Tables → Multiplets 复制粘贴的 tab-separated 文本"。理由：同学不熟悉 Save As CSV 路径，复制粘贴是他能稳定操作的最低成本动作。
- Parser 处理两个 MestReNova 复制粘贴 quirk：(a) 数据行多一个表头未声明的"行号"列；(b) 同学漏复制表头首个 tab 导致表头错位 1 位。检测条件见 `_split_table()`。
- 单峰行末尾 `J's` 空格被吞导致字段数不足 → parser 自动 pad 空串。
- 同学第一次给的样例数据有化学侧问题（杂质峰被 auto multiplet 一并算进同一 multiplet）：总氢数 101、J = 97/81 Hz 异常。Parser 仍**忠实解析**，不在 Phase 3 范围内做 sanity check（留作 Phase 5 拿到结构上下文后再做"H 数 vs 结构氢数"校验）。
- JACS 文本格式 parser（`parse_inline_report`）留作 P1：multiplet 表已经够结构化，第一版不必双轨。

---

# Phase 4：标准 NMR 描述自动生成

## 目标

把结构化 peak list 自动转换成论文/实验记录常用的 NMR 描述格式。

## 输出示例

```text
1H NMR (400 MHz, CDCl3) δ 7.26 (d, J = 8.0 Hz, 2H), 7.10 (d, J = 8.0 Hz, 2H), 3.85 (s, 3H).
```

```text
13C NMR (101 MHz, CDCl3) δ 165.2, 132.1, 129.5, 128.4, 52.1.
```

## TODO

- [x] 实现 1H NMR formatter

  - [x] shift
  - [x] multiplicity
  - [x] J values
  - [x] integration
  - [x] assignment 可选
- [x] 实现 13C NMR formatter

  - [x] shift 列表
  - [x] solvent
  - [x] frequency
- [x] 支持配置输出风格

  - [x] 是否保留 assignment
  - [x] 是否按 shift 从高到低排序
  - [x] 是否显示 solvent
  - [x] 是否显示 frequency
- [x] 添加命令行接口

```bash
chemwf nmr format examples/raw/nmr_multiplet_table_clean_example.tsv --nucleus 1H --frequency 400 --solvent CDCl3
```

## 验收标准

- [x] 输入 MestReNova multiplet 表可以生成规范 NMR 文本
- [x] 1H 和 13C 分别支持
- [x] 输出格式与样例实验记录基本一致
- [x] 至少有 10 个 formatter 单元测试（实际 14 个）

## 可交付物

- [x] `src/chem_workflow/nmr_formatter.py`
- [x] `src/chem_workflow/cli.py`（新增 `chemwf nmr format`）
- [x] `tests/test_nmr_formatter.py`
- [x] `examples/processed/nmr_report.txt`

## 实施备注（2026-05-17）

- Formatter 独立放在 `src/chem_workflow/nmr_formatter.py`，避免继续扩大已有 `nmr.py`；`nmr.py` 仍专注数据模型与 MestReNova multiplet 表解析。
- CLI 新增 `chemwf nmr format`，输入与 Phase 3 保持一致：支持文件路径或 `--inline` 文本，输出默认到 stdout，也可用 `--out` 写文件。
- 默认按 shift 从高到低排序；可用 `--preserve-order` 保留输入顺序。
- 默认隐藏 assignment，因为当前 assignment 多为 MestReNova 字母 ID；需要时可用 `--include-assignment` 显示。
- 默认输出 `frequency` 与 `solvent`；可用 `--hide-frequency` / `--hide-solvent` 隐藏。
- 已生成示例：`examples/processed/nmr_report.txt`。
- 实测：`uv run ruff check .` 全绿；`uv run pytest` 为 75 passed。

---

# Phase 5：实验记录自动生成

## 目标

根据反应信息、产物信息和谱图数据生成实验记录初稿。

## 输入数据模型

```yaml
compound_id: C001
product_name: ethyl benzoate
smiles: CCOC(=O)c1ccccc1
reaction:
  starting_materials:
    - name: benzoic acid
      amount: 1.0 mmol
    - name: ethanol
      amount: 5 mL
  reagents:
    - name: sulfuric acid
      amount: catalytic
  solvent: none
  temperature: reflux
  time: 4 h
workup: diluted with water and extracted with ethyl acetate
purification: column chromatography
appearance: colorless oil
yield:
  mass: 120 mg
  percent: 63%
characterization:
  h1_nmr: ...
  c13_nmr: ...
  hrms: ...
```

## TODO

- [x] 定义 ReactionRecord 数据模型
- [x] 支持从 YAML / JSON 读取实验信息
- [x] 实现英文实验记录模板
- [x] 实现中文实验记录模板
- [x] 支持插入 NMR 描述
- [x] 支持插入 MS / HRMS 描述
- [x] 支持导出 Markdown
- [ ] 支持导出 Word 文档；可作为后续任务（P2，当前 Markdown MVP 不阻塞 Phase 5 验收）

## 第一版模板

```text
Compound {compound_id} was obtained as {appearance}.
To a solution of {starting_materials} in {solvent} was added {reagents}. The reaction mixture was stirred at {temperature} for {time}. The mixture was {workup}. The crude product was purified by {purification} to afford {product_name} ({mass}, {percent}).

1H NMR ...
13C NMR ...
HRMS ...
```

## 验收标准

- [x] 输入 YAML 能生成实验记录 Markdown
- [x] 输出文本中包含反应步骤、纯化、产率和表征数据
- [x] 缺失字段不会导致程序崩溃
- [x] 至少有 5 个记录生成测试（实际 9 个）

## 可交付物

- [x] `src/chem_workflow/records.py`
- [x] `tests/test_records.py`
- [x] `examples/raw/experiment_record_example.yaml`
- [x] `examples/processed/experiment_record.md`
- [x] `templates/experiment_record_en.md`
- [x] `templates/experiment_record_zh.md`

## 实施备注（2026-05-17）

- 新增 `ReactionRecord` / `ReactionInfo` / `Material` / `YieldInfo` / `Characterization` pydantic 模型。
- 新增 `PyYAML` 正式依赖，用于可靠读取 `.yaml/.yml`；同时支持 `.json`。
- 新增 CLI：`chemwf records generate <input.yaml|json> --language en|zh --out record.md`。
- 英文/中文 Markdown 生成采用“字段缺失则省略相关句子”的 MVP 策略，避免用户样例不完整时崩溃。
- 表征字段支持 `h1_nmr`、`c13_nmr`、`hrms`、`ms`、`ir`、`uv` 和 `other`；不会凭空生成数据，只插入结构化输入中已有文本。
- Word 导出保持为 P2：当前验收以 Markdown 为准，后续可接 Documents/Word 工作流。
- 实测：`uv build` 通过；`uv run ruff check .` 全绿；`uv run pytest` 为 84 passed。

---

# Phase 6：本地文件归档与项目管理

## 目标

把每个化合物的数据自动整理成统一文件夹结构。

## 推荐目录结构

```text
ProjectName/
  compounds/
    C001/
      metadata.json
      structure/
        structure.smi
        structure.mol
        structure_indexed.svg
      nmr/
        1H/
          raw/
          peaks.csv
          formatted.txt
        13C/
          raw/
          peaks.csv
          formatted.txt
      ms/
      ir/
      records/
        experiment_record.md
      reports/
        summary.md
```

## TODO

- [ ] 实现 compound folder 初始化

```bash
chemwf init-compound --id C001 --smiles "..."
```

- [ ] 自动创建目录结构
- [ ] 自动生成 `metadata.json`
- [ ] 支持复制原始谱图文件到对应文件夹
- [ ] 支持自动命名文件
- [ ] 支持生成 compound summary

## 验收标准

- [ ] 一条命令可以创建标准化化合物文件夹
- [ ] 文件夹中包含结构、NMR、records 等子目录
- [ ] metadata 中包含 compound_id、smiles、formula、molecular_weight、created_at
- [ ] 重复创建时不会覆盖已有数据，除非显式允许

## 可交付物

- [ ] `src/chem_workflow/storage.py`
- [ ] `examples/project_demo/`

---

# Phase 7：简单 Web UI

## 目标

让不懂编程的化学同学可以通过网页操作。

## 推荐方案

使用 Streamlit 构建本地 Web UI。

## 页面设计

### 页面 1：Compound Setup

- [ ] 输入 compound ID
- [ ] 输入 SMILES
- [ ] 上传 MOL / SDF
- [ ] 显示结构图
- [ ] 显示分子式和分子量

### 页面 2：NMR Formatter

- [ ] 选择 nucleus：1H / 13C / 19F / 31P
- [ ] 输入 frequency
- [ ] 输入 solvent
- [ ] 上传 peak list CSV
- [ ] 预览格式化 NMR 文本
- [ ] 一键复制

### 页面 3：Experiment Record Generator

- [ ] 填写反应条件
- [ ] 填写 workup
- [ ] 填写 purification
- [ ] 填写 yield
- [ ] 自动插入 NMR 文本
- [ ] 生成实验记录 Markdown

### 页面 4：Project Export

- [ ] 选择 compound ID
- [ ] 导出项目文件夹
- [ ] 导出 Markdown 报告
- [ ] 导出 Word 报告；后续可做

## 验收标准

- [ ] 化学同学无需命令行即可完成核心流程
- [ ] 页面能处理错误输入
- [ ] 输出可以复制到实验记录或论文 supporting information

## 可交付物

- [ ] `app.py`
- [ ] `docs/ui_usage.md`
- [ ] Demo 截图

---

# Phase 8：结构—谱图 assignment 辅助

## 目标

实现半自动 NMR assignment 辅助，而不是完全自动解谱。

## 第一版策略

使用规则库 + RDKit 子结构识别 + 人工确认。

## TODO

- [ ] 定义常见 1H NMR 化学位移规则库

```yaml
aromatic_H:
  range: [6.0, 8.5]
  description: aromatic proton
alkyl_CH3:
  range: [0.7, 1.5]
  description: alkyl methyl
OCH3:
  range: [3.2, 4.2]
  description: methoxy proton
aldehyde_H:
  range: [9.0, 10.5]
  description: aldehyde proton
alkene_H:
  range: [4.5, 6.8]
  description: alkene proton
```

- [ ] 使用 RDKit 检测常见官能团

  - [ ] aromatic H
  - [ ] OCH3
  - [ ] alkyl CH3
  - [ ] aldehyde H
  - [ ] alkene H
  - [ ] acidic proton；谨慎处理
- [ ] 对每个 peak 生成候选 assignment

```text
δ 3.85, s, 3H → possible OCH3
δ 7.10–7.30, m, 5H → possible aromatic H
```

- [ ] 标记风险

  - [ ] 积分总数与结构氢数不一致
  - [ ] 芳香区峰数异常
  - [ ] 出现无法解释的强峰
  - [ ] 缺少预期官能团峰
- [ ] 输出 assignment 草稿
- [ ] Web UI 中允许人工确认或修改 assignment

## 验收标准

- [ ] 对简单芳香化合物能给出合理候选归属
- [ ] 对 methoxy、ethyl、tert-butyl 等常见片段能给出候选归属
- [ ] 程序不会声称 assignment 一定正确
- [ ] 每个 assignment 都保留“候选/人工确认”状态

## 可交付物

- [ ] `src/chem_workflow/assignment.py`
- [ ] `data/rules/nmr_1h_rules.yaml`
- [ ] `examples/processed/assignment_draft.md`

---

# Phase 9：LLM 辅助层

## 目标

引入 LLM，但只用于适合语言模型的部分：解释、格式转换、实验记录润色、异常提示总结。

## 适合 LLM 的任务

- [ ] 把结构化实验数据转成自然语言实验记录
- [ ] 把 NMR assignment 草稿整理成可读解释
- [ ] 根据异常检查结果生成提醒
- [ ] 把中文实验记录翻译成英文
- [ ] 把英文实验记录润色成论文 supporting information 风格

## 不建议直接交给 LLM 的任务

- [ ] 仅凭图片直接判断分子结构是否正确
- [ ] 无数据校验地给出唯一 NMR assignment
- [ ] 自动忽略异常峰或杂质峰
- [ ] 在没有结构化输入的情况下生成表征数据

## TODO

- [ ] 设计 LLM 输入 JSON schema
- [ ] 设计 prompt 模板
- [ ] 明确 LLM 输出必须包含 warning 字段
- [ ] 对 LLM 输出做结构化校验
- [ ] 保存 LLM 生成记录，方便回溯
- [ ] 添加人工确认步骤

## 示例 schema

```json
{
  "compound": {
    "compound_id": "C001",
    "smiles": "CCOC(=O)c1ccccc1",
    "formula": "C9H10O2"
  },
  "nmr": {
    "h1": "1H NMR ...",
    "c13": "13C NMR ..."
  },
  "reaction": {
    "temperature": "room temperature",
    "time": "12 h",
    "purification": "column chromatography"
  },
  "checks": [
    "integration total matches expected proton count",
    "aromatic region is consistent with monosubstituted benzene"
  ]
}
```

## 验收标准

- [ ] LLM 只基于结构化输入生成文本
- [ ] LLM 不凭空编造 NMR / MS 数据
- [ ] 输出可被 JSON parser 或 pydantic 校验
- [ ] 所有 LLM 生成文本都标记为 draft

## 可交付物

- [ ] `src/chem_workflow/llm.py`
- [ ] `prompts/experiment_record_en.txt`
- [ ] `prompts/assignment_summary.txt`

---

# Phase 10：MS / HRMS / IR / UV 扩展

## 目标

在 NMR 工作流稳定后，扩展到其他表征数据。

## MS / HRMS TODO

- [ ] 定义 MS 数据模型
- [ ] 支持 calculated mass 和 found mass
- [ ] 自动计算 ppm error
- [ ] 自动生成 HRMS 描述

```text
HRMS (ESI) m/z calculated for C9H10O2Na [M + Na]+ 173.0573, found 173.0570.
```

## IR TODO

- [ ] 支持 IR peak list
- [ ] 标准化单位 cm⁻¹
- [ ] 自动生成 IR 描述

```text
IR (neat) νmax 3050, 2920, 1715, 1600, 1450 cm⁻¹.
```

## UV TODO

- [ ] 支持 λmax
- [ ] 支持 solvent
- [ ] 支持 absorbance 或 epsilon

```text
UV-vis (MeOH) λmax 254 nm.
```

## 验收标准

- [ ] MS / HRMS 可以生成标准描述
- [ ] IR 可以生成标准描述
- [ ] UV 可以生成标准描述
- [ ] 所有新增模块都有测试

## 可交付物

- [ ] `src/chem_workflow/ms.py`
- [ ] `src/chem_workflow/ir.py`
- [ ] `src/chem_workflow/uv.py`

---

# Phase 11：文献和历史数据检索

## 目标

帮助同学快速找到类似化合物、历史实验和已有表征数据。

## 本地历史数据检索

- [ ] 建立 SQLite 数据库
- [ ] 保存 compound metadata
- [ ] 保存 NMR / MS / IR 数据
- [ ] 支持按 compound ID 搜索
- [ ] 支持按 SMILES 搜索
- [ ] 支持按子结构搜索
- [ ] 支持按相似度搜索

## 文献检索；后续增强

- [ ] 通过 DOI / paper title 记录文献来源
- [ ] 保存文献中的 NMR 数据
- [ ] 对比当前化合物和文献化合物
- [ ] 给出相似结构的历史谱图参考

## 验收标准

- [ ] 可以检索本地做过的化合物
- [ ] 可以根据结构相似度找到历史样例
- [ ] 可以复用历史实验记录模板

## 可交付物

- [ ] `src/chem_workflow/search.py`
- [ ] `src/chem_workflow/database.py`
- [ ] `data/chem_workflow.sqlite`

---

# Phase 12：稳定性、测试与交付

## 目标

让工具从 demo 变成同学能长期使用的小工具。

## TODO

- [ ] 增加完整测试集
- [ ] 增加错误处理
- [ ] 增加日志
- [ ] 增加数据备份机制
- [ ] 增加配置文件
- [ ] 增加用户文档
- [ ] 增加常见问题说明
- [ ] 打包为本地可运行应用

## 验收标准

- [ ] 非程序员可以按文档安装和运行
- [ ] 输入错误时不会崩溃
- [ ] 原始实验数据不会被覆盖
- [ ] 每个输出都能追溯到输入文件
- [ ] 至少完成 5 个真实化合物的端到端测试

## 可交付物

- [ ] `docs/user_guide.md`
- [ ] `docs/dev_guide.md`
- [ ] `docs/faq.md`
- [ ] release zip 或安装脚本

---

# Agent 可执行任务模板

后续可以把任务按下面格式交给 agent。

## 任务模板

```markdown
## Task: <任务名称>

### Context
我们正在开发一个化学工作流自动化工具。当前目标是：<当前阶段目标>。

### Input
- 已有文件：
- 样例数据：
- 相关模块：

### Requirements
- [ ] requirement 1
- [ ] requirement 2
- [ ] requirement 3

### Expected Output
- 文件 1：
- 文件 2：
- 测试：

### Acceptance Criteria
- [ ] 可以通过 pytest
- [ ] 可以运行示例命令
- [ ] 输出与 expected output 一致

### Constraints
- 不要修改无关模块
- 不要删除原始数据
- 新增函数需要 type hints
- 新增逻辑需要测试
```

---

# 推荐的第一批 Agent 任务

## Agent Task 1：搭建 Python 项目骨架

```markdown
## Task: Initialize Python project skeleton

### Context
We are building a Python toolkit for chemistry workflow automation.

### Requirements
- Create project structure under `chem-ai-workflow/`
- Add `pyproject.toml`
- Add `README.md`
- Add `src/chem_workflow/__init__.py`
- Add `src/chem_workflow/cli.py`
- Add basic Typer CLI with `chemwf --help`
- Add pytest setup

### Expected Output
- Runnable Python package
- Passing empty pytest suite
- CLI help command works

### Acceptance Criteria
- `pip install -e .` works
- `chemwf --help` works
- `pytest` works
```

## Agent Task 2：实现 SMILES 解析与结构图生成

```markdown
## Task: Implement structure parser with RDKit

### Context
The toolkit should read a SMILES string, validate it, and generate basic molecular metadata.

### Requirements
- Implement `parse_smiles(smiles: str)`
- Return canonical SMILES, formula, molecular weight
- Implement `draw_structure_with_atom_indices(smiles: str, output_path: str)`
- Add CLI commands for parsing and drawing
- Add unit tests

### Expected Output
- `src/chem_workflow/structure.py`
- `tests/test_structure.py`

### Acceptance Criteria
- Valid SMILES returns correct metadata
- Invalid SMILES raises clear error
- SVG or PNG structure image can be generated
```

## Agent Task 3：实现 NMR peak list CSV parser

```markdown
## Task: Implement NMR peak list parser

### Context
The toolkit should parse exported or manually created NMR peak lists into a structured format.

### Requirements
- Define `NMRPeak` and `NMRSpectrum` models
- Parse CSV with columns: shift_ppm, integration, multiplicity, j_hz, assignment, note
- Normalize multiplicity values
- Normalize J values into list of floats
- Add tests for common formats

### Expected Output
- `src/chem_workflow/nmr.py`
- `tests/test_nmr.py`
- Example CSV file

### Acceptance Criteria
- CSV can be parsed into structured JSON
- Invalid values produce clear errors
- Tests cover at least 10 cases
```

## Agent Task 4：实现 NMR formatter

```markdown
## Task: Implement NMR text formatter

### Context
The toolkit should generate publication-style NMR descriptions from structured peak data.

### Requirements
- Format 1H NMR text
- Format 13C NMR text
- Support solvent and frequency
- Sort peaks from high ppm to low ppm
- Add CLI command
- Add tests

### Expected Output
- Formatter function in `nmr.py`
- CLI command `chemwf nmr format`
- Tests and example output

### Acceptance Criteria
- Example peak CSV generates expected NMR text
- 1H and 13C are both supported
```

## Agent Task 5：实现实验记录生成器

```markdown
## Task: Generate experiment record from YAML

### Context
The toolkit should generate a draft experiment record from structured reaction and characterization data.

### Requirements
- Define reaction record schema
- Read YAML input
- Generate English Markdown experiment record
- Insert NMR text if available
- Handle missing fields gracefully
- Add tests

### Expected Output
- `src/chem_workflow/records.py`
- `templates/experiment_record_en.md`
- `examples/processed/experiment_record.md`

### Acceptance Criteria
- YAML input generates readable Markdown
- Missing optional fields do not crash the program
- Tests pass
```

---

# 开发原则

## 永远保留人工确认

所有 assignment、异常判断、LLM 生成内容都必须是 draft，不能直接当作最终结论。

## 先结构化，再 AI

优先把数据变成 JSON / CSV / YAML，再让 LLM 辅助解释和生成文本。

## 不要覆盖原始数据

所有原始谱图、实验文件、结构文件都应放在 `raw/` 目录，程序只在 `processed/` 下生成新文件。

## 小步快跑

每个阶段都要有可以运行的 demo，而不是等到最后才整合。

## 面向非程序员

最终界面要尽量做到：上传文件、填写表单、复制结果。

---

# 最小可用版本定义

MVP 只需要完成以下功能：

- [ ] 输入 compound ID 和 SMILES
- [ ] 生成结构图和分子基本信息
- [ ] 读取 1H NMR peak list CSV
- [ ] 生成标准 1H NMR 描述
- [ ] 读取反应 YAML
- [ ] 生成英文实验记录 Markdown
- [ ] 自动整理到 compound 文件夹

完成这些后，就已经能显著改善化学同学的记录和整理工作流。
