# `src` 功能化目录与 Agent SDK 接入重构计划

## 计划元数据

- 状态：**Completed**
- 创建日期：2026-08-31
- 工作分支：`codex/src-functional-refactor`
- 基线分支：`dev`
- 基线提交：`908f1bb`（`Ensure cross-platform CI and path handling`）
- 范围：`src/chem_workflow/`、根目录 `app.py`、相关测试与开发文档

## 1. 背景

当前 `src/chem_workflow/` 约有 20 个同级 Python 模块，共约 6,048 行；根目录
`app.py` 另有约 1,470 行。项目已经完成从结构解析、谱学格式化、实验记录、归档、
assignment、历史检索到 LLM 辅助的主要功能，但源码目录仍沿用早期 MVP 的扁平结构。

当前主要结构问题：

1. 功能边界不够直观：结构、谱学、归档、数据库、LLM、CLI/UI 支撑全部平铺。
2. 部分模块职责过多：
   - `assignment.py`：模型、规则、特征检测、分配、警告和 Markdown 渲染。
   - `database.py`：模型、SQLite repository、归档导入、文献库和 Typer 命令。
   - `cli.py`：多个领域的命令实现和根命令注册。
   - `app.py`：七个页面、共享组件、状态管理和业务编排。
3. 接口边界不一致：部分 Typer 命令在 `cli.py`，部分放在 `ms.py`、`ir.py`、
   `uv.py`、`database.py` 和 `config.py` 中。
4. `models.py` 是空占位文件，继续使用全局模型文件容易演变成无明确归属的聚合点。
5. assignment rules 和 prompts 通过 `Path(__file__).parents[...]` 定位仓库根资源；移动模块后
   路径会变化，而且当前资源不适合作为可靠的已安装包资源使用。
6. 后续计划使用封装好的 Agent SDK。若直接让 SDK 类型、Runner、handoff 或 tracing 进入
   化学领域模块，会形成新的供应商耦合并再次触发重构。

当前质量基线：

- `uv run pytest -q`：226 passed, 1 skipped。
- `uv run ruff check .`：通过。
- CLI、Streamlit AppTest 和黄金输出回归均已存在，可作为渐进重构的行为锚点。

## 2. 目标

1. 按用户能理解的业务功能组织源码，而不是按技术名词建立大型横向目录。
2. 将确定性的化学逻辑与 Typer、Streamlit、OpenAI/Agent SDK 解耦。
3. 将现有自写 LLM call、client protocol 和手工 orchestration 标记为 deprecated，并迁移到
   选定 Agent SDK 的原生 Agent/Runner、structured output、guardrail、session 和 tracing 能力。
4. 保持项目自己的输入/输出 schema、化学工具和人工确认策略稳定，但不再维护通用的自写
   Agent runtime protocol。
5. 保持 CLI 命令、UI 文案、session-state key、输出格式和文件安全策略兼容。
6. 解决 rules、prompts 等资源在源码移动和 wheel 安装后的定位问题。
7. 以小批次迁移，每个阶段都能独立通过测试并可审查。

## 3. 非目标

- 不在本次重构中改变 NMR/HRMS/assignment 算法或化学规则。
- 不把已有确定性流程改造成 LLM/Agent 流程。
- 不同时引入多个 Agent SDK；先选择一个 canonical SDK 并使用其原生 API。
- 不预先设计可覆盖所有 SDK 的通用 `AgentRuntime Protocol` 或自写 orchestration framework。
- 不修改用户数据目录结构、SQLite schema 或黄金输出格式。
- 不重做 Streamlit 的视觉设计。
- 不为了“分层完整”创建大量只有一两个函数的微型文件。
- 不在本计划中重组整个 `tests/` 目录；仅按源码迁移需要更新 import 和增加架构测试。

## 4. 目标目录结构

```text
src/chem_workflow/
  __init__.py

  core/
    __init__.py
    config.py
    logging.py
    resources.py

  compounds/
    __init__.py
    structure.py

  spectroscopy/
    __init__.py
    nmr/
      __init__.py
      models.py
      parsing.py
      formatting.py
      consistency.py
    assignment/
      __init__.py
      models.py
      rules.py
      features.py
      service.py
      rendering.py
    hrms.py
    ir.py
    uv.py

  records/
    __init__.py
    models.py
    io.py
    rendering.py

  archive/
    __init__.py
    models.py
    service.py

  history/
    __init__.py
    models.py
    repository.py
    importers.py
    search.py

  ai/
    __init__.py
    context.py
    schemas.py
    agents/
      __init__.py
      record_polisher.py
      assignment_reviewer.py
      compound_analyst.py
    workflows/
      __init__.py
      record_polish.py
      assignment_review.py
      compound_analysis.py
    tools/
      __init__.py
      structure.py
      spectroscopy.py
      records.py
      history.py
      archive.py
    sdk/
      __init__.py
      bootstrap.py           # 选定 SDK 的配置与初始化边界

  interfaces/
    __init__.py
    cli/
      __init__.py
      main.py
      structure.py
      nmr.py
      assignment.py
      spectra.py
      records.py
      archive.py
      history.py
      ai.py
      config.py
    web/
      __init__.py
      main.py
      pages/
        __init__.py
        compound.py
        nmr.py
        spectra.py
        records.py
        archive.py
        assignment.py
        history.py
      components/
        __init__.py
        common.py
        llm.py
        state.py

  resources/
    prompts/
    assignment_rules/

app.py                       # 薄 Streamlit 启动器
```

最终文件名可以在迁移阶段按实际职责微调，但顶层功能边界和依赖方向不得反转。

## 5. 架构与依赖规则

```text
CLI / Streamlit
      |
      v
AI workflow / Agent definition
      |
      v
选定 Agent SDK 的原生 Agent / Runner / Result
      |
      v
typed tools ----------> compounds / spectroscopy / records / archive / history
      |
      v
core
```

必须遵守以下规则：

1. `compounds`、`spectroscopy`、`records`、`archive`、`history` 不得导入 Typer、
   Streamlit 或任何 Agent SDK。
2. `interfaces` 可以依赖功能包；功能包不得反向依赖 `interfaces`。
3. `ai/tools` 只能包装稳定的功能 API，不复制化学逻辑。
4. Agent SDK 类型只允许出现在 `ai/agents`、`ai/workflows`、`ai/sdk` 和相应接口适配代码中。
5. 新代码不得直接调用 OpenAI Responses/Chat Completions，或依赖 deprecated
   `LLMClientProtocol`；模型调用统一由 Agent SDK 承担。
6. 不创建全局 `utils.py` 或大型 `models.py`；共享代码必须有明确业务归属。
7. `__init__.py` 只导出稳定公共 API，不执行数据库连接、环境读取或 Agent 初始化。
8. 同步/异步转换集中在 SDK workflow 或 interface 边界，不在各页面和工具中散布
   `asyncio.run()`。

## 6. Agent SDK 接入策略

### 6.1 三类任务

| 任务形态 | 推荐实现 |
|---|---|
| 解析、格式化、HRMS 计算、规则 assignment | 确定性 Python 功能包 |
| 实验记录润色、warning 摘要等单次生成 | Agent SDK + structured output |
| 多工具、多步骤、需要状态或 delegation 的分析 | Agent SDK 原生 tools / handoff / session |

不得仅为了使用 Agent SDK 而把确定性任务 Agent 化。

### 6.2 Deprecated 范围与退出策略

以下自写调用与编排层进入 deprecated：

- `OpenAIResponsesClient`；
- `LLMClientProtocol`；
- 手工 Responses / Chat Completions API mode 分支；
- 手工 tool/model 调用循环和 response JSON 提取兼容逻辑；
- 仅为 fake client 而存在的自定义 runtime protocol。

以下内容不因迁移而弃用：

- Pydantic 输入/输出 schema；
- prompt 内容和版本信息；
- 化学规则、确定性 validators 和 post-processing；
- warnings、人工确认状态、run metadata 等产品契约；
- 当前 CLI/UI 调用的 workflow 函数名；其内部实现迁移到 Agent SDK。

弃用规则：

1. 从本计划开始，不再给旧 call/protocol 增加新功能。
2. 项目仍为 `0.0.1`，尚未发布稳定 Python API；所有 workflow 迁移后直接删除旧实现，
   不维护会延长两套调用路径寿命的 legacy fallback。
3. `ai/agents`、`ai/workflows` 和 `interfaces` 只使用 SDK 原生 Agent/Runner/model 类型。
4. 离线测试 patch SDK Runner/model 边界，不再实现 fake client protocol。
5. 架构测试禁止旧 symbol 或直接 OpenAI client import 回流。

### 6.3 使用 SDK 原生抽象

- 首个 canonical Agent SDK 直接使用其 Agent、Runner、Result、context/session、guardrail 和
  tracing 类型。
- 项目只维护业务输入/输出 schema、agent instructions、tool wrappers 和人工确认策略。
- 测试优先使用 SDK 提供的 model/provider 注入或测试能力，不再创建项目级通用 client protocol。
- 若未来确实需要第二个 SDK，再基于两个真实实现提取最小共同边界；本次不做推测性抽象。
- UI/CLI 仍只调用项目 workflow 函数，不直接构造 Agent 或 Runner。

### 6.4 Tools 与副作用

第一批 Agent tools 只暴露只读能力：

- 结构解析和 metadata；
- NMR/IR/UV 输入解析和格式化；
- HRMS 计算；
- consistency 检查；
- 历史数据查询。

以下操作必须显式标记为有副作用，并在 UI/CLI 层取得人工确认后才能执行：

- 写入或覆盖归档文件；
- 写入 SQLite 历史库；
- 删除记录；
- 复制原始实验文件；
- 任何会影响用户现有数据的操作。

### 6.5 SDK 依赖策略

- canonical SDK 选用 OpenAI Agents SDK；项目原有 AI 功能是正式能力，因此 SDK 作为正常
  项目依赖安装，而不是同时保留自写 fallback。
- 核心离线化学功能包不得 import Agent SDK；该约束由架构测试保证。
- tracing、handoff、session 等使用 SDK 原生能力，并将必要字段映射为项目产品 schema。
- 真实 API 测试继续使用 `integration` marker，默认单元测试不得要求 API key 或网络。

## 7. 兼容与资源策略

### 7.1 Python import

- 迁移期间为当前常用 import 路径提供薄 re-export，避免一次性修改所有消费者。
- 项目内部 import 在对应阶段切换到新 canonical 路径。
- 兼容模块只能显式导出名称，不使用无约束的 `import *`。
- 是否删除兼容入口放到最终清理阶段，并以仓库内引用和用户文档为依据。

### 7.2 CLI 与 UI

- 保持 `chemwf` 命令名、subcommand、参数名、退出码和主要输出不变。
- `pyproject.toml` 的脚本入口可以暂时继续指向兼容 `chem_workflow.cli:app`。
- 根目录 `app.py` 保留为启动器，确保 `run.bat`、`run.sh` 和 AppTest 路径不变。
- 第一轮 Web 拆分保留现有导航文案、widget key 和 session-state key，不同时迁移 UI 交互模式。

### 7.3 包资源

- 将 prompts 和 assignment rules 迁入 `chem_workflow/resources/` 或建立等价的正式 package-data
  方案。
- 统一通过 `importlib.resources` 或 `core.resources` 访问，不再依赖调用模块的目录深度。
- `uv build` 后检查 wheel 内容，并在临时环境从已安装 wheel 执行 prompt/rules smoke test。

## 8. 分阶段执行计划

### Phase 0：建立安全网与资源路径

- [x] 记录当前模块、公共符号、CLI command tree 和测试基线（见
  `docs/generated/src_refactor_baseline.md`）。
- [x] 新增架构/import 测试，禁止领域包导入 Typer、Streamlit 和 Agent SDK。
- [x] 建立 `core.resources`，迁移 prompts 和 assignment rules 的定位方式。
- [x] 配置并验证 wheel package data。
- [x] 验证源代码运行和已安装 wheel 两种模式。

验收：

- 原有 226 个非集成测试继续通过。
- prompt 和 1H/13C assignment rules 在仓库与 wheel 环境都可读取。
- 不改变任何用户输出。

实施记录（2026-08-31）：prompts 与 1H/13C assignment rules 已迁入
`src/chem_workflow/resources/`，wheel 内容和隔离导入 smoke test 通过；新增资源及架构测试，
相关 37 个测试通过。

### Phase 1：建立功能包骨架与公共 API

- [x] 创建 `core`、`compounds`、`spectroscopy`、`records`、`archive`、`history`、`ai`、
  `interfaces` 包骨架。
- [x] 将 config/logging 移入 `core`，保留必要兼容入口。
- [x] 明确每个包的公共 API 和 `__all__`。
- [x] 删除或替代空的顶层 `models.py`。

验收：

- 新包可以独立 import，且 `__init__.py` 无初始化副作用。
- 旧 CLI 和测试仍能运行。

### Phase 2：统一 CLI 接口层

- [x] 从 `ms.py`、`ir.py`、`uv.py`、`database.py`、`config.py` 抽出 Typer 命令。
- [x] 将现有 `cli.py` 按功能拆到 `interfaces/cli/`。
- [x] `interfaces/cli/main.py` 只负责根 callback 和 sub-app 注册。
- [x] 保留 `chemwf` 当前命令树。

验收：

- 领域模块不再 import Typer。
- CLI 测试、错误码和 `chemwf --help` / subcommand `--help` 通过。

### Phase 3：迁移低耦合化学与谱学模块

- [x] `structure.py` → `compounds/structure.py`。
- [x] `nmr.py` / `nmr_formatter.py` / `consistency.py` → `spectroscopy/nmr/`。
- [x] `ms.py` → `spectroscopy/hrms.py`。
- [x] `ir.py` / `uv.py` → `spectroscopy/`，暂不进一步拆成微文件。
- [x] 更新内部 import，并提供必要兼容 re-export。

验收：

- 所有结构、NMR、MS、IR、UV、consistency 测试通过。
- 黄金输出逐字不变。

### Phase 4：拆分大型业务模块

- [x] 按模型、规则、特征、服务、渲染拆分 `assignment.py`。
- [x] 按模型、输入和渲染拆分 `records.py`。
- [x] 按模型与服务拆分 `storage.py` 到 `archive/`。
- [x] 按模型、repository、归档导入和纯检索拆分 `database.py` / `search.py`。
- [x] 保持 SQLite schema、文件目录结构和人工确认语义不变。

验收：

- 不再存在同时承担模型、持久化、CLI 和渲染的单个大型模块。
- assignment、records、storage、database、search 测试全部通过。
- 归档默认不覆盖原始数据。

### Phase 5：弃用自写 LLM 调用层并迁移到 Agent SDK

- [x] 盘点 `llm_models.py`、`llm.py`、`llm_cli.py` 的公共 API，将 schema、workflow、
  post-processing 与自写调用/协议代码分开。
- [x] 选定 OpenAI Agents SDK `0.20.0` 作为 canonical SDK 并加入项目依赖。
- [x] 删除 `OpenAIResponsesClient`、`LLMClientProtocol`、手工模型调用和 response parsing；
  项目尚未发布稳定 Python API，因此不保留长期 legacy fallback。
- [x] 使用 SDK 原生 Agent、Runner、structured output 和 tracing 迁移现有四个 LLM workflow，
  保持当前公开 workflow 函数、输出 schema 和人工确认语义。
- [x] 将现有 prompt 加载、post-processing 和 run persistence 分离并复用，不重写有效业务校验。
- [x] 为结构 metadata、HRMS、IR、UV 定义只读 typed SDK tool wrappers。
- [x] 使用 SDK 自身的 Agent/Runner/model 边界完成离线单元测试，不新增通用 fake client protocol。
- [x] 实现只读 `compound_analysis` 多工具 pilot workflow。
- [x] pilot 不暴露任何副作用工具；未来新增写工具时必须先实现显式 approval gate。
- [x] 确认源码中不存在 `ai/legacy`、旧 call/protocol 或直接模型 API 调用。

验收：

- compounds / spectroscopy / records / archive / history 等核心包不依赖 Agent SDK。
- 现有 LLM 单元测试保持离线通过。
- 所有 AI workflow 均通过选定 Agent SDK 执行，不再直接调用 Responses/Chat Completions。
- 新代码不再 import `LLMClientProtocol`、`OpenAIResponsesClient` 或 `ai.legacy`。
- pilot 返回 schema-valid 结果，并保留必要的 SDK trace/run metadata。
- deprecated call/protocol 在迁移窗口结束后已删除，不作为长期 fallback。

### Phase 6：拆分 Streamlit Web 接口

- [x] 根目录 `app.py` 改为薄启动器。
- [x] 七个工作流页面迁入 `interfaces/web/pages/`。
- [x] 下载、状态、LLM 展示等共享 UI 代码迁入 `components/`。
- [x] 页面只调用功能服务或 AI workflows，不直接构造具体 SDK client。
- [x] 保持现有 widget key、页面标题、按钮文案和 session-state 行为。

验收：

- `tests/test_app.py` 全部通过。
- 七个页面均可启动，现有用户路径不变。
- `app.py` 仅保留配置、导航和启动职责。

### Phase 7：清理、文档与完成

- [x] 搜索并迁移仓库内旧 canonical import。
- [x] 将旧顶层模块缩减为显式 re-export，保留已有脚本与测试的兼容价值。
- [x] 更新 `docs/dev_guide.md`、README 和相关用户文档。
- [x] 记录如何新增谱学模块、Agent definition、tool 和 workflow，以及禁止新增自写 call/protocol。
- [x] 运行完整测试、Ruff、build 和 wheel smoke test。
- [x] 将本计划状态改为 Completed，移入 `docs/exec-plans/completed/` 并更新引用。

完成记录（2026-08-31）：

- `uv run pytest -q`：236 passed, 1 skipped。
- `uv run ruff check .`：通过。
- `uv build`：sdist 与 wheel 构建成功。
- wheel 隔离 smoke：package resources、功能包、Agent tools、CLI/Web 入口均可导入。
- `chemwf --help` 命令树保持兼容；Streamlit 七页 AppTest 全部通过。

## 9. 每阶段验证命令

```bash
uv run ruff check .
uv run pytest
uv build
uv run chemwf --help
```

按影响范围补充：

- 对受影响 subcommand 执行 `--help` 和最小成功/失败 smoke test。
- 运行 `tests/test_app.py` 检查 Streamlit。
- 运行 `tests/test_expected_outputs.py` 检查黄金输出。
- 在临时环境安装 wheel 后测试 package resources。
- Agent SDK 真实调用只在显式 integration 环境执行。

## 10. 主要风险与控制措施

| 风险 | 控制措施 |
|---|---|
| 移动模块导致 import 大面积失效 | 分阶段迁移、兼容 re-export、每阶段跑完整测试 |
| `__file__` 相对路径失效 | Phase 0 先完成正式 package resource 迁移 |
| Typer 命令树或错误码变化 | 保留命令注册顺序和 CLI 测试，逐命令 smoke test |
| Streamlit widget/session 状态丢失 | 第一轮保持 key 和导航文案，AppTest 锚定行为 |
| 新包产生循环依赖 | 架构 import 测试，领域包禁止依赖 interfaces/SDK |
| Agent SDK 类型泄漏到核心化学功能 | 功能包 import 边界测试；只有 `ai` / `interfaces` 使用 SDK |
| 再次出现自写 orchestration | 架构测试禁止新代码 import legacy call/protocol 或直接调用模型 API |
| SDK 类型泄漏到领域模块 | SDK 类型只允许存在于 `ai` 和接口适配边界 |
| Agent 执行意外写数据 | 只读 tools 先行，副作用工具必须 approval gate |
| 同步 UI 与异步 Runner 冲突 | 在 SDK workflow/interface 边界集中处理 async 生命周期 |

## 11. 完成定义

只有同时满足以下条件，计划才可标记完成：

- 源码已按目标功能边界组织，领域模块不依赖 Typer、Streamlit 或 Agent SDK。
- `assignment.py`、`database.py`、`cli.py`、`app.py` 的多职责大文件已被合理拆分。
- 当前 CLI、UI、SQLite、归档和黄金输出行为保持兼容。
- prompts/rules 在源码和 wheel 环境都能稳定读取。
- 现有 LLM workflow 已迁移到选定 Agent SDK，并保持 structured output 产品契约。
- 自写 LLM call、`LLMClientProtocol` 和 direct Responses orchestration 已删除，不再作为 fallback。
- 至少有 SDK-native 离线测试和一个受控的多工具 pilot。
- 所有默认测试、Ruff、build 和 wheel smoke test 通过。
- 开发者文档已更新，本计划已移入 `completed/` 并同步索引。
