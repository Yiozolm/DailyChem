# 产品需求规格：DailyChem · chem-ai-workflow

> 本文档把 `docs/references/requirements-dialog.md`（与化学同学的原始需求对话）和各 Phase
> 已落定的决策整理为正式需求规格，作为后续开发的范围依据。

## 1. 背景与用户画像

- **开发者**：懂编程、不懂化学。
- **目标用户**：懂化学、不(太)懂编程的合成方向研究生 / 科研人员。
- **使用场景**：日常做大量合成实验，需要整理结构、谱图数据，写实验记录与论文 supporting information。

## 2. 核心痛点（来自需求对话）

1. **实验记录最烦**：做实验量极大，手写 / 整理实验记录耗时且枯燥。
2. **谱图归属琐碎**：拿到实测谱后，要为每个峰找结构上的归属（化学位移 + 耦合裂分），与预测谱比对。
3. **表征数据格式化**：NMR / MS / IR / UV 数据要整理成论文规范文本。

> 注：同学用 ChemDraw 预测谱辅助比对，但"AI 自动解谱"被明确认为目前不可靠，故本工具
> **不做全自动解谱**，只做稳定、可解释、可人工确认的半自动辅助。

## 3. 支持范围（第一版）

### 结构输入
- 接受：SMILES、`.mol`、`.sdf`、ChemDraw `.cdx` / `.cdxml`、`.smi`。
- RDKit 原生解析 `.cdx`/`.cdxml`（详见 `docs/design-docs/cdx-handling-spike.md`）。

### NMR
- 输入：MestReNova `View → Tables → Multiplets` 复制的 tab-separated 文本，兼容常见 comma/semicolon CSV；13C/19F/31P 也接受纯化学位移列表。
- publication-style 文本：支持 **1H / 13C / 19F / 31P**。
- assignment：规则库 + RDKit 子结构/碳类型的 **1H / 13C 候选归属草稿**，始终保留人工确认状态。
- 一致性检查：用结构对称性数出理论唯一信号数，与实测峰数比对（「对得上/对不上」的轻量判断），不预测化学位移数值。

### MS / IR / UV（Phase 10）
- HRMS：从结构 + adduct 自动算 calc m/z，或手动输入；自动算 ppm error。
- IR / UV-vis：波数 / λmax 列表 → 标准表征文本。

### 实验记录
- 输入：反应信息 YAML / JSON。
- 输出：**中文 / 英文** Markdown 初稿，自动插入已有表征文本。

### LLM 辅助（Phase 9，可选）
- 仅消费结构化输入，润色记录 / 整理 assignment 摘要；输出恒为 draft + warnings，不编造数据。

### 历史检索（Phase 11）
- 本地 SQLite 库；按 compound ID / SMILES / 子结构 / 相似度检索历史化合物。
- 文献参考：手录 DOI / 标题 / SMILES / 报道 NMR，并按结构相似度对照当前化合物。

## 4. 明确不做（边界）

- **全自动解谱**：不凭结构或谱图图像自动给唯一 assignment 定论。
- **图像反推 peak list**：不从谱图截图反推数值（精度差、丢积分）。
- **仪器原始数据**：不接 Bruker / JEOL / Agilent 原始数据目录（fid/acqus 等）。
- **Word / PDF 导出**：MVP 只做 Markdown / 文本 / zip。
- **真实科研数据样例**：项目无法获得脱敏的真实数据，样例均为合成 / 脱敏数据。

## 5. 输出格式约定

结构 metadata + atom-indexed SVG、NMR JSON、publication-style NMR/MS/IR/UV 文本、
实验记录 Markdown、compound 归档文件夹 + summary。参考样例见 `examples/expected_outputs/`。

## 6. 文件命名约定

实际样例遵循的命名惯例（供后续保持一致）：

- 结构样例：`compound_<name>_<variant>.<ext>`，如 `compound_b_single.mol`、`synthesis_route_cys.cdx`。
- NMR 输入：`nmr_multiplet_table_<variant>_example.tsv`。
- 谱学输入样例：`<kind>_peaks_example.txt`（`ir_peaks_example.txt`、`uv_peaks_example.txt`）、`ms_hrms_example.txt`。
- compound 归档内：`structure.{smi,mol}`、`structure_indexed.svg`、`metadata.json`、`reports/summary.md`。
- 谱学导出文本：`<compound-id>_<kind>.txt`（UI 下载默认名），归档内 `nmr/1H/formatted.txt` 等。

## 7. 验收依据

各 Phase 验收以 `tests/` 自动化测试 + `examples/expected_outputs/` 黄金输出回归为准
（详见 `docs/exec-plans/active/chem_ai_workflow_todo.md` 各 Phase 验收标准）。
