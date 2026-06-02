# DailyChem · chem-ai-workflow

化学工作流自动化工具：结构、谱图、实验记录的半自动处理。

详细规划见 [`docs/exec-plans/active/chem_ai_workflow_todo.md`](docs/exec-plans/active/chem_ai_workflow_todo.md)。

## 安装

依赖 [uv](https://docs.astral.sh/uv/) 和 Python ≥ 3.11。

```bash
uv sync
```

## 运行

### 启动图形界面（推荐给非程序员用户）

Mac / Linux：

```bash
bash run.sh
```

Windows：

双击 `run.bat`，或在终端运行：

```bat
run.bat
```

默认会在浏览器打开 DailyChem 页面。若没有自动打开，可访问终端提示的本地地址，
通常是 `http://localhost:8501`。

完整的端到端使用指南（面向化学同学）见 [`docs/user_guide.md`](docs/user_guide.md)，
常见问题见 [`docs/faq.md`](docs/faq.md)。

### 命令行工具（开发者）

```bash
uv run chemwf --help
uv run chemwf version
```

### NMR peak list 格式化

第一版接收 MestReNova `View → Tables → Multiplets` 复制出来的 tab-separated 文本：

```bash
uv run chemwf nmr parse examples/raw/nmr_multiplet_table_clean_example.tsv --frequency 400 --solvent CDCl3
uv run chemwf nmr format examples/raw/nmr_multiplet_table_clean_example.tsv --frequency 400 --solvent CDCl3
```

### 实验记录生成

```bash
uv run chemwf records generate examples/raw/experiment_record_example.yaml
uv run chemwf records generate examples/raw/experiment_record_example.yaml --language zh --out examples/processed/experiment_record.md
```

### Compound 本地归档

```bash
uv run chemwf init-compound --id C001 --project-dir examples/project_demo --smiles "CCOC(=O)c1ccccc1"
```

### 本地 Web UI（开发者原始命令）

```bash
uv run streamlit run app.py
```

更详细的界面使用说明见 [`docs/ui_usage.md`](docs/ui_usage.md)。

### 1H NMR assignment 草稿

```bash
uv run chemwf nmr assign examples/raw/nmr_multiplet_table_clean_example.tsv \
  --smiles "CCOC(=O)c1ccccc1" \
  --frequency 400 \
  --solvent CDCl3
```

该命令只生成候选归属和风险提示，不会声称自动 assignment 一定正确。

### MS / IR / UV 表征文本

```bash
uv run chemwf ms hrms --smiles "CCOC(=O)c1ccccc1" --adduct "[M+Na]+" --found 173.0570
uv run chemwf ir format examples/raw/ir_peaks_example.txt
uv run chemwf uv format examples/raw/uv_peaks_example.txt --solvent MeOH
```

### 本地历史检索

```bash
uv run chemwf db add --id C001 --smiles "CCOC(=O)c1ccccc1"
uv run chemwf db search --smiles "c1ccccc1" --substructure
uv run chemwf db search --smiles "CCOC(=O)c1ccccc1" --similarity --threshold 0.5
```

### 配置与备份

```bash
uv run chemwf config init          # 生成 .chemwf.toml（图形界面默认值来源）
uv run chemwf config show
uv run chemwf backup --id C001 --project-dir examples/project_demo
```

## 测试

```bash
uv run pytest
```

## 代码风格

```bash
uv run ruff check .
uv run ruff format .
```

## 目录结构

- `src/chem_workflow/` —— 源代码（按 phase 分模块占位）
- `tests/` —— pytest 测试
- `data/{raw,processed}/` —— 本地数据，默认不入库
- `examples/{raw,expected_outputs}/` —— 样例输入与期望输出
- `docs/` —— 项目文档（产品、设计、执行计划等）
