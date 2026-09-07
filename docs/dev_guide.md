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
  core/             配置、日志、package resources
  compounds/        结构解析、metadata、绘图
  spectroscopy/
    nmr/            models / parsing / formatting / consistency
    assignment/     models / rules / features / service / rendering
    hrms.py / ir.py / uv.py
  records/          实验记录 models / io / rendering
  archive/          compound 归档 models / service
  history/          SQLite repository、归档导入、结构检索
  ai/               Agent SDK schemas、agents、workflows、tools、SDK bootstrap
  interfaces/
    cli/            Typer 根入口与按功能拆分的 sub-app
    web/            Streamlit 入口、页面与共享组件
  resources/        随 wheel 分发的 prompts 与 assignment rules
  *.py              旧 import 路径的薄兼容入口
app.py              Streamlit 薄启动器
tests/              pytest（与模块一一对应 + test_app / test_expected_outputs）
examples/           raw 输入样例 + expected_outputs 黄金输出
docs/               产品 / 设计 / 执行计划 / 用户文档
```

## 模块职责一句话

| 模块 | 职责 |
|---|---|
| compounds | 一切"分子 → RDKit Mol / 基本信息 / 图" |
| spectroscopy.nmr | peak 模型、解析、格式化与一致性检查 |
| spectroscopy.assignment | 候选归属，永远带人工确认状态 |
| records | 结构化反应信息 → 记录 Markdown |
| spectroscopy.hrms / ir / uv | 各谱的 model、parser、formatter |
| ai | Agent SDK 只消费结构化输入，输出 draft + warnings |
| history | 历史沉淀与结构检索 |
| archive | 归档与备份，只读源、不覆盖 |
| core | 配置、日志与只读 package resources |
| interfaces | Typer / Streamlit 交付层，不承载化学算法 |

## 加一个新谱学模块（套路）

以 `spectroscopy/hrms.py`、`ir.py`、`uv.py` 为模板：

1. **数据模型**：pydantic `BaseModel`，列表默认值用 `Field(default_factory=...)`，枚举用 `Literal[]`。
2. **错误类**：`XxxInputError(ValueError)`，中文 docstring，消息含可操作建议。
3. **parser 与 formatter 分离**：`parse_*` 负责"输入 → model"，`format_*` 负责"model → 文本"。
4. **领域模块不导入 Typer/Streamlit**：命令放在 `interfaces/cli/`，页面放在 `interfaces/web/`。
5. **注册**：在 `interfaces/cli/main.py` 注册 sub-app，保持现有命令风格。
6. **UI（可选）**：页面复用领域函数，默认值从 `core.config` 读取。
7. **测试**：`tests/test_xxx.py`，单元 + `CliRunner` CLI + `pytest.raises(match=...)`；需要时加黄金输出回归。

## 加一个 Agent workflow（套路）

1. 输入/输出 schema 放 `ai/schemas.py` 或对应功能 schema 模块。
2. Agent definition 放 `ai/agents/`，直接使用选定 Agents SDK 的原生 Agent/Runner 类型。
3. 确定性能力包装为 `ai/tools/` typed tool；不得复制化学逻辑。
4. 应用入口放 `ai/workflows/`，CLI/UI 只调用 workflow，不直接构造 SDK client。
5. 不新增自写 LLM call、`LLMClientProtocol` 或手工 Responses/Chat Completions parsing。
6. 默认测试 patch SDK Runner/model 边界；真实 API 调用继续使用 `integration` marker。

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
