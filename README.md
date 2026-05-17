# DailyChem · chem-ai-workflow

化学工作流自动化工具：结构、谱图、实验记录的半自动处理。

详细规划见 [`docs/exec-plans/active/chem_ai_workflow_todo.md`](docs/exec-plans/active/chem_ai_workflow_todo.md)。

## 安装

依赖 [uv](https://docs.astral.sh/uv/) 和 Python ≥ 3.11。

```bash
uv sync
```

## 运行

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

### 本地 Web UI

```bash
uv run streamlit run app.py
```

使用说明见 [`docs/ui_usage.md`](docs/ui_usage.md)。

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
