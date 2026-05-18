# DailyChem Streamlit UI 使用说明

Phase 7 新增本地 Web UI，目标是让不熟悉命令行的化学同学也能完成核心流程：
结构检查、NMR 文本格式化、实验记录生成和 compound 项目归档。

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

- `1H`
- `13C`

`19F` / `31P` 已在 UI 中预留入口，但格式化规则会放到后续 phase 扩展。格式化结果会显示为
可复制代码块，Streamlit 代码块右上角提供 copy 图标；也可以下载为 `.txt`。

## 页面 3：Experiment Record Generator

填写反应条件、workup、purification、yield 和 characterization 后，点击
**生成 Markdown**。

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

## 页面 4：Project Export

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

## 页面 5：NMR Assignment Draft

该页面用于生成 `1H NMR` 候选 assignment 草稿。它会结合结构特征和
`data/rules/nmr_1h_rules.yaml` 里的规则，为每个 peak 给出 possible candidates、
confidence 和 warning。

重要原则：

- 输出是 candidate，不是最终结论。
- 每一行都有 review status：`candidate` / `needs_review` / `confirmed`。
- `confirmed` 只能在人工核对结构和原始谱图后手动标记。
- 可以在表格中人工修改 `selected_assignment` 和 `manual_note`。

## 当前限制

- Web UI 是本地辅助工具，不做用户权限或服务器部署设计。
- NMR formatter 目前只支持 `1H` / `13C` publication-style 输出。
- Assignment assistant 目前只支持 `1H NMR` 候选归属。
- Word 报告导出暂未实现，当前推荐先使用 Markdown。
