# 开发者指南

## 技术栈

- Python ≥ 3.11，包管理 **uv**
- RDKit（结构 / 指纹 / 子结构）、pydantic（数据模型）、Typer（CLI）、Streamlit（UI）
- pytest（测试）、ruff（lint + format）、SQLite（标准库，历史库）

## 常用命令

```bash
uv sync                 # 安装依赖
uv run pytest           # 跑测试
uv run ruff check .     # lint
uv run ruff format .    # 格式化
uv run chemwf --help    # CLI 入口
uv run streamlit run app.py   # 图形界面
```

## 项目结构

```text
src/chem_workflow/
  structure.py      结构解析（SMILES/MOL/SDF/CDX）、mol_info、绘图
  nmr.py            MestReNova multiplet 表解析、NMR 数据模型
  nmr_formatter.py  1H/13C publication-style 文本
  assignment.py     规则库 + RDKit 子结构 → 1H 候选归属草稿
  records.py        ReactionRecord 模型 + 中/英实验记录 Markdown
  storage.py        compound 归档文件夹 + 备份
  ms.py / ir.py / uv.py   HRMS / IR / UV-vis 数据模型 + parser + formatter
  llm.py / llm_models.py / llm_cli.py   OpenAI 结构化输出辅助层
  database.py       本地 SQLite 历史库 + db 子命令
  search.py         子结构 / 相似度检索
  config.py         .chemwf.toml 配置
  logging_setup.py  轻量日志
  cli.py            Typer 根入口，注册各 sub-app
app.py              Streamlit 单文件 UI（复用以上模块，不重复化学逻辑）
tests/              pytest（与模块一一对应 + test_app / test_expected_outputs）
examples/           raw 输入样例 + expected_outputs 黄金输出
docs/               产品 / 设计 / 执行计划 / 用户文档
```

## 模块职责一句话

| 模块 | 职责 |
|---|---|
| structure | 一切"分子 → RDKit Mol / 基本信息 / 图" |
| nmr / nmr_formatter | peak 表解析 与 文本格式化（分离） |
| assignment | 候选归属，永远带人工确认状态 |
| records | 结构化反应信息 → 记录 Markdown |
| ms / ir / uv | 各谱：model + parser + formatter |
| llm | 仅消费结构化输入，输出 draft + warnings |
| database / search | 历史沉淀与结构检索 |
| storage | 归档与备份，只读源、不覆盖 |
| config / logging_setup | 交付化基础设施 |

## 加一个新谱学模块（套路）

以现有 `ms.py` / `ir.py` / `uv.py` 为模板：

1. **数据模型**：pydantic `BaseModel`，列表默认值用 `Field(default_factory=...)`，枚举用 `Literal[]`。
2. **错误类**：`XxxInputError(ValueError)`，中文 docstring，消息含可操作建议。
3. **parser 与 formatter 分离**：`parse_*` 负责"输入 → model"，`format_*` 负责"model → 文本"。
4. **模块内 Typer app**：`xxx_app = typer.Typer(...)`，命令风格照搬现有（`--inline`/文件、`--json`、`--out`）。
5. **注册**：在 `cli.py` `import xxx_app` 并 `app.add_typer(xxx_app, name="xxx")`。
6. **UI（可选）**：在 `app.py` 复用模块函数，默认值尽量从 `CONFIG` 取。
7. **测试**：`tests/test_xxx.py`，单元 + `CliRunner` CLI + `pytest.raises(match=...)`；需要时加黄金输出回归。

## 测试约定

- 测试用 `tmp_path`，**不依赖网络 / 真实 API key**。
- 测试中的仓库文件入口必须从 `Path(__file__)` 推导，不能假设 pytest 当前工作目录。
- 写入 JSON / Markdown 的相对路径统一使用 `Path.as_posix()`，保证 Windows / Linux 输出一致。
- LLM 真实调用走 `@pytest.mark.integration`，默认跳过（见 `pyproject.toml` markers）。
- 改动输出格式时，同步重新生成 `examples/expected_outputs/`（见该目录 README）并提交。

## 持续集成

`.github/workflows/quality.yml` 在以下情况自动运行：

- push 到 `main` 或 `dev`
- pull request
- GitHub Actions 手动触发

测试矩阵覆盖 Ubuntu / Windows 与 Python 3.11 / 3.13，每个组合都运行 pytest 和 Ruff。

## 提交前检查

```bash
uv run ruff check .
uv run pytest
```

两者都过再提交。
