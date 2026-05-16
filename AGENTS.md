# Project Agent Instructions

## 项目文档目录

项目文档统一放在 `docs/` 下，入口索引是 `docs/README.md`。后续 agent 应先从本节和 `docs/README.md` 了解当前文档结构。

### Outline

- `docs/`: 项目文档根目录。
  - `README.md`
  - `product-specs/`
  - `design-docs/`
  - `exec-plans/`
    - `active/`
    - `completed/`
  - `generated/`
  - `references/`

### Maintenance Rules

1. 按要求完成 `docs/exec-plans/active/` 内的计划后，必须同步更新对应文档状态。
2. 活跃执行计划完成后移入 `docs/exec-plans/completed/`，并更新相关引用。
3. 新文档按用途分别放入 `product-specs/`、`design-docs/`、`exec-plans/`、`generated/` 或 `references/`。
4. 不要写出过大的文件；保持架构化、模块化设计，保证代码和文档都可扩展。
5. 使用 uv 进行python项目的包管理