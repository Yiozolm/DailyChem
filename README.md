# DailyChem · chem-ai-workflow

化学工作流自动化工具：结构、谱图、实验记录的半自动处理。

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
- `docs/` —— 项目文档占位骨架（详细规划在开发分支维护）
