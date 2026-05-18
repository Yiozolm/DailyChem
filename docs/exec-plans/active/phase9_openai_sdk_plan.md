# Phase 9 OpenAI SDK LLM 辅助层执行计划

## 背景

项目当前已完成结构解析、NMR peak list parsing / formatting、实验记录 Markdown 生成、本地归档、Streamlit UI，以及 rule-based `1H` NMR assignment draft。

Phase 9 的目标不是替代这些确定性模块，而是在结构化数据已经可用的前提下，用 OpenAI SDK 做适合 LLM 的语言层辅助：

- 把结构化实验信息润色为更自然的英文实验记录 draft
- 把 rule-based assignment draft 整理成可读解释
- 把异常检查结果总结成面向化学同学的提醒
- 把中文实验记录翻译或润色为英文 supporting information 风格

所有 LLM 输出必须保持 `draft` 状态，并保留人工确认步骤。

## 官方参考依据

- OpenAI Python SDK 官方库建议以 `OpenAI()` client 调用 Responses API，并默认从 `OPENAI_API_KEY` 读取 API key；如需兼容代理、自建网关或 OpenAI-compatible endpoint，可在 client 初始化时显式传入 `base_url`。
  - https://github.com/openai/openai-python
- OpenAI Structured Outputs 支持用 Python `pydantic.BaseModel` 配合 `client.responses.parse(..., text_format=...)` 得到 schema-adherent 输出。
  - https://developers.openai.com/api/docs/guides/structured-outputs
- Responses API 支持 `instructions`、`input`、`model`、`metadata`、`store`、`reasoning` 等参数；Python / JavaScript SDK 提供 `output_text` convenience property。
  - https://platform.openai.com/docs/api-reference/responses
- OpenAI model guide 建议复杂 reasoning / coding 从 `gpt-5.5` 开始；若优化 latency / cost，可选 `gpt-5.4-mini` 或 `gpt-5.4-nano`。
  - https://developers.openai.com/api/docs/models

## 设计原则

1. **先结构化，再 LLM**
   - LLM 只能消费已有 `ReactionRecord`、NMR text、assignment draft、warning list 等结构化输入。
   - 不让 LLM 从图片、谱图截图或非结构化猜测中生成表征数据。

2. **输出必须可校验**
   - 统一使用 Pydantic output schemas。
   - 首选 OpenAI SDK `client.responses.parse(..., text_format=SomeBaseModel)`。
   - 禁止只让模型返回自由文本后直接写入最终报告。

3. **永远保留人工确认**
   - 输出 schema 必须包含 `status: "draft"`。
   - 输出必须包含 `warnings`。
   - CLI / UI 文案明确提示：不能直接作为最终 assignment 或 supporting information。

4. **不编造化学数据**
   - Prompt 明确禁止新增 NMR / MS / HRMS / IR / UV 数值。
   - 后处理检查模型输出是否出现输入中不存在的新表征数值；发现则标记 warning 或拒绝写出正式 Markdown。

5. **可追溯**
   - 每次 LLM run 保存模型、prompt version、输入摘要/hash、输出 JSON、warnings、created_at、OpenAI request id（如 SDK 可获得）。
   - 不保存 API key，不写入 `.env`。

## 推荐模型策略

第一版采用可配置模型，不把具体模型强绑定到业务逻辑：

| 场景 | 默认建议 | 理由 |
|---|---|---|
| 常规实验记录润色、翻译、warning summary | `gpt-5.4-mini` | 成本 / latency 更适合频繁本地工具调用 |
| 高质量英文 supporting information polish | `gpt-5.5` | 对长文本、复杂写作质量要求更高 |
| 测试和低成本快速预览 | `gpt-5.4-nano` | 仅用于简单格式转换或 UI demo |

配置优先级：

1. CLI 参数：`--model`
2. 环境变量：`CHEMWF_OPENAI_MODEL`
3. 默认值：`gpt-5.4-mini`

`base_url` 也需要作为一等配置项，便于兼容不同部署方式：

1. CLI 参数：`--base-url`
2. 环境变量：`OPENAI_BASE_URL`
3. 环境变量：`CHEMWF_OPENAI_BASE_URL`
4. 默认值：不显式设置，使用 OpenAI SDK 默认 endpoint

API key 只通过环境变量读取：

```bash
export OPENAI_API_KEY="..."
# optional, for proxy / compatible endpoint
export OPENAI_BASE_URL="https://api.openai.com/v1"
```

同时应补充 `.env.example`，并把 `.env` 加入 `.gitignore`。

## 目标用户故事

### Story 1：根据结构化 YAML 生成英文实验记录 draft

```bash
chemwf llm draft-record examples/raw/experiment_record_example.yaml \
  --style supporting-information \
  --out examples/processed/experiment_record_llm_draft.json
```

输入：

- `ReactionRecord`
- 已有 deterministic renderer 生成的 baseline Markdown
- 已有 characterization strings

输出：

- structured JSON
- draft Markdown
- warnings
- source field usage summary

### Story 2：整理 NMR assignment draft 为可读解释

```bash
chemwf llm summarize-assignment examples/processed/assignment_draft.md \
  --out examples/processed/assignment_summary_llm.json
```

输入：

- rule-based assignment draft
- detected features
- warnings

输出：

- 面向人工复核的解释
- unresolved peaks
- review checklist
- explicit disclaimer

### Story 3：根据异常检查结果生成提醒

```bash
chemwf llm summarize-warnings assignment_draft.json \
  --out examples/processed/warning_summary_llm.json
```

输出要求：

- 不替用户做最终判断
- 按 severity 排序
- 给出下一步人工检查建议

### Story 4：中文实验记录翻译 / 英文润色

```bash
chemwf llm polish-record record.md \
  --language en \
  --style supporting-information \
  --out polished_record.json
```

输出要求：

- 保留所有数值、单位、化合物编号
- 不新增表征字段
- 对不确定表达写入 warning

## 文件改动计划

### 新增文件

```text
src/chem_workflow/llm.py
tests/test_llm.py
prompts/
  experiment_record_en.txt
  assignment_summary.txt
  warning_summary.txt
  polish_record.txt
.env.example
docs/exec-plans/active/phase9_openai_sdk_plan.md
```

### 修改文件

```text
pyproject.toml
.gitignore
src/chem_workflow/cli.py
app.py
docs/ui_usage.md
docs/exec-plans/active/chem_ai_workflow_todo.md
```

说明：

- `app.py` 和 `docs/ui_usage.md` 只在 CLI MVP 稳定后再接入。
- `chem_ai_workflow_todo.md` 应在 Phase 9 实施完成后同步勾选状态；计划阶段暂不勾选 TODO。

## 模块设计

### `src/chem_workflow/llm.py`

建议职责：

1. OpenAI SDK client wrapper
2. LLM input / output Pydantic schemas
3. Prompt loading and versioning
4. Structured output generation
5. Post-generation validation
6. LLM run persistence

建议核心类型：

```python
class OpenAISettings(BaseModel):
    model: str = "gpt-5.4-mini"
    base_url: str | None = None
    timeout_seconds: float = 60.0
    max_output_tokens: int = 4000
    store: bool = False


class LLMWarning(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warning", "risk"] = "warning"


class LLMRunMetadata(BaseModel):
    task: str
    model: str
    prompt_version: str
    created_at: datetime
    input_hash: str
    request_id: str | None = None


class ExperimentRecordDraft(BaseModel):
    status: Literal["draft"] = "draft"
    title: str
    markdown: str
    warnings: list[LLMWarning]
    source_fields_used: list[str]
    unsupported_claims: list[str] = Field(default_factory=list)


class AssignmentSummaryDraft(BaseModel):
    status: Literal["draft"] = "draft"
    summary_markdown: str
    unresolved_items: list[str]
    review_checklist: list[str]
    warnings: list[LLMWarning]
```

SDK wrapper 应该是可测试的：

```python
class LLMClientProtocol(Protocol):
    def parse_response(...) -> BaseModel:
        ...
```

单元测试使用 fake client，不依赖网络。

## CLI 设计

新增 Typer 子命令：

```text
chemwf llm draft-record <input.yaml|json>
chemwf llm summarize-assignment <assignment.md|json>
chemwf llm summarize-warnings <input.json>
chemwf llm polish-record <record.md>
```

通用参数：

```text
--model
--base-url
--out
--save-run / --no-save-run
--runs-dir
--max-output-tokens
--dry-run-prompt
```

错误处理：

- 未设置 `OPENAI_API_KEY`：给出清晰提示，不打印 stack trace。
- OpenAI API 连接失败 / rate limit / auth failure：转换成项目内 `LLMInputError` 或 `LLMServiceError`。
- schema parse 失败：保存 raw error summary，但不输出最终 Markdown。

## Prompt 设计

所有 prompt 模板必须包含以下硬约束：

1. Use only the structured input.
2. Do not invent characterization data.
3. Preserve all numeric values, units, compound IDs, solvent names, and nucleus labels.
4. If data is missing or ambiguous, add a warning instead of guessing.
5. Return `status = "draft"`.
6. Include warnings even when the list is empty.
7. Do not claim assignment certainty; use possible / candidate / requires review.

Prompt 文件头建议记录：

```text
Prompt-Version: 2026-05-18-v1
Task: experiment_record_en
Output-Schema: ExperimentRecordDraft
```

## 后处理校验

第一版实现轻量校验即可：

- 检查输出 `status == "draft"`
- 检查 `warnings` 字段存在
- 对 characterization 数值做 conservative scan：
  - 如果输出中出现新的 `NMR`、`HRMS`、`MS`、`IR`、`UV` 数字模式，但输入 characterization 中不存在，加入 `unsupported_claims`
  - 若 `unsupported_claims` 非空，CLI 默认只写 JSON，不写 standalone Markdown
- 检查输出中是否包含“confirmed assignment”“proved assignment”等过度确定措辞
- 检查 prompt / run log 不包含 `OPENAI_API_KEY`

## 数据保存策略

默认保存到：

```text
<project-dir>/compounds/<compound_id>/llm_runs/
```

若没有 compound archive context，则保存到用户指定 `--runs-dir`，或不保存。

建议文件：

```text
llm_runs/
  20260518_153000_experiment_record_en/
    input.json
    output.json
    metadata.json
    prompt.txt
```

注意：

- 原始输入可包含实验数据，但不能包含 API key。
- 默认 `store=False`，避免远端保存响应；如用户明确需要 dashboard 检索，可通过参数开启。

## Streamlit UI 计划

CLI MVP 完成后再接入 UI：

1. Experiment Record Generator 页面增加 “LLM polish draft” 按钮
2. NMR Assignment Draft 页面增加 “Summarize for review” 按钮
3. UI 必须展示：
   - Draft badge
   - Warnings
   - “Copy draft” 按钮
   - “I reviewed this” 手动确认 checkbox
4. API key 不在 UI 表单中长期保存；优先读取环境变量。

## 测试计划

### 单元测试；默认运行，无网络

- `OpenAISettings` 环境变量读取与默认值
- prompt loader 能读取并识别 prompt version
- fake client 返回合法 schema 后能通过 Pydantic validation
- fake client 返回缺字段 / 非 draft 状态时被拒绝
- post-check 能发现新增 characterization claim
- CLI 在缺 `OPENAI_API_KEY` 时给出可读错误
- `--dry-run-prompt` 不调用 SDK

### Integration test；默认跳过

使用 marker：

```python
@pytest.mark.integration
```

仅当存在环境变量时运行：

```bash
CHEMWF_RUN_OPENAI_INTEGRATION=1 OPENAI_API_KEY=... uv run pytest -m integration
```

### 回归样例

- `examples/raw/experiment_record_example.yaml`
- `examples/processed/assignment_draft.md`
- 至少一个中文记录片段

## 验收标准

- [ ] `openai` SDK 已加入 `pyproject.toml`，`.env` 已加入 `.gitignore`
- [ ] `chemwf llm draft-record` 可以从 YAML/JSON 生成 schema-valid JSON draft
- [ ] `chemwf llm summarize-assignment` 可以把 assignment draft 转为人工复核摘要
- [ ] 所有 LLM 输出都包含 `status: "draft"` 和 `warnings`
- [ ] 缺少 API key、认证失败、rate limit、schema mismatch 都有清晰错误
- [ ] 默认测试不需要真实 OpenAI API key
- [ ] 至少一个 integration test 可在用户提供 API key 时运行
- [ ] Streamlit UI 至少能调用实验记录 polish 或 assignment summary 中的一个
- [ ] `docs/exec-plans/active/chem_ai_workflow_todo.md` Phase 9 状态同步更新

## 分阶段实施顺序

### Step 1：SDK 基础与安全配置

- 加 `openai>=2,<3`
- 加 `.env.example`
- `.gitignore` 加 `.env`
- 实现 `OpenAISettings`
- 实现缺 API key 的友好错误

### Step 2：Schema 与 prompt

- 定义 `ExperimentRecordDraft`、`AssignmentSummaryDraft`、`LLMWarning`
- 新增 prompt templates
- 加 prompt version 读取

### Step 3：OpenAI wrapper；mockable

- 用 `OpenAI().responses.parse(...)`
- 初始化 client 时支持 `OpenAI(base_url=settings.base_url)`；`base_url=None` 时走 SDK 默认值
- 支持 `model`、`instructions`、`input`、`metadata`、`store=False`
- 捕获 OpenAI SDK exceptions
- 记录 request id

### Step 4：CLI MVP

- `chemwf llm draft-record`
- `chemwf llm summarize-assignment`
- `--dry-run-prompt`
- `--out`

### Step 5：Run log 与后处理校验

- 保存 input/output/metadata/prompt
- 实现 unsupported characterization claim scan
- Markdown 输出必须经过 schema + post-check

### Step 6：Streamlit UI 接入

- 先接实验记录 polish
- 再接 assignment summary
- UI 展示 draft/warnings/review checkbox

### Step 7：文档与验收

- 更新 `docs/ui_usage.md`
- 更新 `chem_ai_workflow_todo.md`
- 运行：

```bash
uv run ruff check .
uv run pytest
uv run chemwf llm draft-record examples/raw/experiment_record_example.yaml --dry-run-prompt
```

## 暂不做的事情

- 不做 ChatGPT-style 多轮 agent
- 不让 LLM 调工具或直接读取本地文件系统
- 不让 LLM 自动决定最终 NMR assignment
- 不从谱图图片中反推 peak list
- 不生成输入里不存在的 MS / HRMS / IR / UV / NMR 数据
- 不把 OpenAI API key 写入配置文件或日志

## 推荐下一步

先实现 Step 1–4，形成 CLI-only MVP。等 CLI 的 schema、错误处理和测试稳定后，再接入 Streamlit UI。

## 实施进展（2026-05-18）

已完成 CLI-only MVP：

- [x] Step 1：SDK 基础与安全配置
  - `pyproject.toml` 增加 `openai>=2,<3`
  - `.env.example` 增加 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`CHEMWF_OPENAI_MODEL`
  - `.gitignore` 增加 `.env`
  - `OpenAISettings` 支持 `model`、`base_url`、`timeout_seconds`、`max_output_tokens`、`store`
  - 补充内置 `.env` loader：默认从当前目录向上查找 `.env`，不覆盖已有环境变量；也支持 `CHEMWF_ENV_FILE` 指向显式 dotenv 文件
- [x] Step 2：Schema 与 prompt
  - 新增 `src/chem_workflow/llm_models.py`
  - 新增 `ExperimentRecordDraft`、`AssignmentSummaryDraft`、`LLMWarning`、`LLMRunMetadata`
  - 新增 `prompts/experiment_record_en.txt`
  - 新增 `prompts/assignment_summary.txt`
  - 预留 `prompts/warning_summary.txt`、`prompts/polish_record.txt`
- [x] Step 3：OpenAI wrapper；mockable
  - 新增 `OpenAIResponsesClient`
  - 使用懒加载 `openai`，默认单元测试不需要 SDK 网络调用
  - 支持 `OpenAI(base_url=settings.base_url)`；未设置时走 SDK 默认 endpoint
  - 支持 `api_mode=responses | chat-completions`；OpenAI-compatible gateway 若不支持 `/responses`，可切到 `chat-completions`
  - DeepSeek 兼容：`chat-completions` 模式走 `client.chat.completions.create(...)`，支持 `DEEPSEEK_API_KEY`、`reasoning_effort` 和 `extra_body` thinking enabled
  - 对常见 404 增加可操作诊断：检查 base_url 是否误填完整 endpoint、provider 是否支持 `/responses`、model 是否存在
  - fake client 可测试 structured-output pipeline
- [x] Step 4：CLI MVP
  - 新增 `src/chem_workflow/llm_cli.py`，避免继续扩大根 CLI 文件
  - 新增 `chemwf llm draft-record`
  - 新增 `chemwf llm summarize-assignment`
  - 两个命令均支持 `--dry-run-prompt`、`--model`、`--base-url`、`--api-mode`、`--out`
- [x] 部分 Step 5：Run log 与后处理校验
  - 支持 `--save-run` 保存 input/output/metadata/prompt
  - 实现 spectroscopy 数值新增的 conservative scan
  - 实现 assignment 过度确定措辞 warning

已验证：

```bash
uv run ruff check .
uv run pytest
uv run chemwf llm draft-record examples/raw/experiment_record_example.yaml --dry-run-prompt
```

结果：`ruff` 全绿，`pytest` 为 117 passed。

尚未完成：

- Streamlit UI 接入
- `summarize-warnings` / `polish-record` CLI 正式接线
- 真实 OpenAI API integration test；默认仍跳过，避免测试依赖 API key / 网络
- 人工确认 UI 状态持久化
