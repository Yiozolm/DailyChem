# DailyChem Streamlit UI 使用说明

Phase 7 新增本地 Web UI，目标是让不熟悉命令行的化学同学也能完成核心流程：
结构检查、NMR 文本格式化、MS/IR/UV 表征、实验记录生成、compound 项目归档和历史检索。

Demo 截图：[`docs/generated/phase7_streamlit_demo.png`](generated/phase7_streamlit_demo.png)

## 启动

推荐使用一键启动脚本，不需要记住完整的 Streamlit 命令。

Mac / Linux：

```bash
bash run.sh
```

Windows：

双击项目根目录下的 `run.bat`，或在终端运行：

```bat
run.bat
```

开发者也可以使用原始命令：

```bash
uv run streamlit run app.py
```

默认会在浏览器打开 Streamlit 页面。若没有自动打开，可访问终端提示的本地地址，
通常是 `http://localhost:8501`。

## 页面 1：Compound Setup

支持两种结构输入：

- 直接输入 SMILES。
- 上传结构文件：`.mol`、`.sdf`、`.cdx`、`.cdxml`、`.smi`、`.smiles`。

点击 **解析结构** 后，页面会显示：

- canonical SMILES
- 分子式
- 分子量
- heavy atom 数
- 带 atom index 的结构 SVG

解析出的 canonical SMILES 会自动保存到当前 UI 会话，供实验记录和项目导出页面复用。

## 页面 2：NMR Formatter

输入 MestReNova `View → Tables → Multiplets` 导出的 peak list。推荐使用 tab-separated
文本；也支持常见 comma / semicolon CSV。可以上传 `.tsv` / `.csv` / `.txt`，也可以
直接粘贴表格内容。

当前 publication-style formatter 支持：

- `1H`（带 multiplicity / J / 积分）
- `13C` / `19F` / `31P`（位移列表）

格式化结果会显示为可复制代码块，Streamlit 代码块右上角提供 copy 图标；也可以下载为 `.txt`。

格式化后的 `1H` / `13C` 文本会保存到当前会话，自动带入实验记录页的对应 characterization 字段。

## 页面 3：MS / IR / UV

把 HRMS、IR、UV-vis 数据整理成标准表征文本。页面分三个 tab：

- **HRMS**：calculated m/z 有两种来源——
  - *从结构自动计算*：输入 SMILES + 选择 adduct（`[M+H]+` / `[M+Na]+` / `[M+K]+` /
    `[M+NH4]+` / `[M-H]-` / `[M+H-H2O]+`），程序用 RDKit 单同位素质量自动算 m/z 和离子式；
  - *手动输入 calc m/z*：直接填 ion formula 和 calculated m/z。
  - 可选填 found m/z，自动计算 ppm error。输出例：
    `HRMS (ESI) m/z calculated for C9H10O2Na [M + Na]+ 173.0573, found 173.0570 (ppm error -1.7).`
- **IR**：粘贴波数列表（逗号/空白/换行分隔，可带强度如 `1715 s`），可选 technique（neat / KBr / ATR）。
  输出例：`IR (neat) νmax 3050, 2920, 1715, 1600, 1450 cm⁻¹.`
- **UV-vis**：粘贴 λmax 列表（可带 ε，如 `254 (12000)`），可选 solvent。
  输出例：`UV-vis (MeOH) λmax 254 nm (ε 12000), 320 nm (ε 4500).`

每个 tab 生成的文本都保存到当前会话，自动带入实验记录页的 HRMS / IR / UV-vis 字段，也可单独下载。

## 页面 4：Experiment Record Generator

填写反应条件、workup、purification、yield 和 characterization 后，点击
**生成 Markdown**。

HRMS / IR / UV-vis 字段会自动填入上一页生成的文本（如果有）。

Starting materials 和 reagents 推荐每行一个条目：

```text
benzoic acid | 1.0 mmol
ethanol | 5 mL
```

也支持轻量 comma 写法：

```text
benzoic acid, 1.0 mmol
```

若前一步已经格式化过 `1H` 或 `13C` NMR，相关文本会自动进入 characterization 输入框。

## 页面 5：Project Export

Project Export 会调用 Phase 6 的归档逻辑，创建标准 compound 文件夹：

```text
<project-dir>/compounds/<compound-id>/
```

页面支持：

- 使用当前 canonical SMILES / 手动输入 SMILES / 上传结构文件初始化 compound。
- 可选复制当前生成的实验记录到 `records/`。
- 生成 `metadata.json`、结构文件和 `reports/summary.md`。
- 下载 `summary.md`。
- 下载 compound 文件夹 zip。

默认不覆盖已有 compound；如需重新生成，必须显式勾选 **允许覆盖已有 metadata / summary**。

## 页面 6：NMR Assignment Draft

该页面用于生成 `1H` / `13C` NMR 候选 assignment 草稿。选好核种后，它会结合结构特征和
规则库（`data/rules/nmr_1h_rules.yaml` 或 `nmr_13c_rules.yaml`），为每个 peak 给出
possible candidates、confidence 和 warning。1H 用 MestReNova multiplet 表，13C 用化学位移列表。

结果区顶部会显示**理论信号数一致性**判断：把结构理论上应有的唯一信号数（RDKit 对称性）
与实测峰数对比——一致（绿色）/ 实测偏多 / 实测偏少（黄色），帮助快速判断「对不对得上」。

重要原则：

- 输出是 candidate，不是最终结论。
- 每一行都有 review status：`candidate` / `needs_review` / `confirmed`。
- `confirmed` 只能在人工核对结构和原始谱图后手动标记。
- 可以在表格中人工修改 `selected_assignment` 和 `manual_note`。

## 页面 7：History Search

把做过的化合物沉淀到本地 SQLite 历史库，并按结构检索历史样例。页面顶部可指定数据库路径
（默认 `data/chem_workflow.sqlite`），下分两个 tab：

- **入库**：
  - *从归档批量导入*：填项目根目录，扫描其中所有 `compounds/*/metadata.json` 并导入（会尽力带上已生成的谱学文本）。
  - *添加当前化合物*：用当前会话的 compound ID / SMILES（以及已生成的 HRMS / IR / UV / NMR 文本）一键入库。
- **检索**：输入 SMILES 或 SMARTS，选择检索方式——
  - *子结构*：返回包含该子结构的所有历史化合物；
  - *相似度*：用 Morgan 指纹 + Tanimoto，按可调阈值过滤并按分数降序展示。
  - 结果以表格显示 compound ID / 分子式 / 分子量 / 相似度分数 / SMILES。
- **文献**：录入文献参考（DOI + SMILES + 可选 1H/13C 文本），并按相似度对照当前化合物，
  展示相似文献报道的 NMR 数据，供人工比对。

历史库只存本地，不随 git 提交。

## LLM 辅助（draft，可选）

Phase 9 在两个页面接入了可选的 LLM 辅助按钮。两者都遵循"先结构化，再 LLM"的原则：
LLM 只消费页面里已经生成的结构化文本，**不会**凭空编造 NMR / MS / HRMS / IR / UV 数据。

- **Experiment Record 页**：生成 Markdown 后，下方出现 **✨ LLM 润色草稿** 按钮，
  把记录润色成 supporting-information 风格。
- **NMR Assignment 页**：生成草稿后，下方出现 **📝 Summarize for review** 按钮，
  把候选归属整理成可读的复核摘要。

每个 LLM 区块都有一个 **LLM 设置（可选）** 折叠面板，可填写 model、base URL 和 API mode
（`responses` / `chat-completions`）。API key **不在页面收集**，只从环境变量或项目根目录
`.env` 读取（`OPENAI_API_KEY`，DeepSeek 用 `DEEPSEEK_API_KEY`）。

输出始终标记为 **DRAFT**，并展示：

- 按 severity 排序的 warnings（`info` / `warning` / `risk`）。
- 可复制 / 下载的 Markdown 草稿。
- **✅ I reviewed this draft** 人工确认复选框（仅当前会话有效，刷新即重置）。

LLM 草稿不能直接作为最终结论或论文 supporting information，必须人工复核后再使用。

## 当前限制

- Web UI 是本地辅助工具，不做用户权限或服务器部署设计。
- NMR formatter 支持 `1H` / `13C` / `19F` / `31P`；assignment 候选归属支持 `1H` / `13C`。
- HRMS adduct 目前支持单电荷常见集合（`[M+H]+` / `[M+Na]+` / `[M+K]+` / `[M+NH4]+` / `[M-H]-` / `[M+H-H2O]+`）。
- 一致性检查只比对**信号数**，不预测化学位移数值。
- 文献检索为本地手录条目 + 结构对照，不做在线 DOI 解析 / 全文抓取。
- LLM 人工确认状态只存当前 Streamlit 会话，刷新页面会丢失。
- Word 报告导出暂未实现，当前推荐先使用 Markdown。
