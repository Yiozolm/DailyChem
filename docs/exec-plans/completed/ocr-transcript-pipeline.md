# OCR 改为逐页转录 + 代码解析 + 计量校验

状态：已完成（2026-10-31）

## 背景

用 `examples/raw/note/1-5.jpg` 对旧流程（长 JSON prompt + 补充转录）做基线测试：

- 模型转录质量好，但结构化映射差：用量列常被填成分子量或当量；溶剂进入 reagents；
  转录中已有的重结晶、产量、外观没有进入字段。
- note 5 的 JSON prompt 触发重复循环，跑满 4096 tokens 后整页丢失；同一页用 GLM-OCR 原生
  `Text Recognition:` prompt 可以正常输出。
- 手写 µ 几乎总被识别为 m（µL→mL、µmol→mmol），差 1000 倍。

## 范围

1. 每张照片单独发送 `Text Recognition:`，不再要求模型输出 JSON；单页失败只记 warning。
2. 新增 `ocr/transcript.py`：清理 LaTeX、解析试剂表（空格表格与 Markdown 表格）、按句子
   拆分 procedure / workup / purification / 产率 / 外观。
3. 新增 `ocr/stoichiometry.py`：检查 n = m/M、V = m/d、当量比、产率；发现 1000 倍差异时
   提示 µ/m 误识别。只给 warning，不自动改值。
4. Records 页面显示解析后的试剂表；表单已有产物 SMILES 时，用 RDKit 分子量复核产率。

不在范围：更换 OCR 模型、图片缩放/缓存、批量导入、8080 外部服务配置。

## 验收

- `uv run pytest` 与 `uv run ruff check` 通过。
- 5 张示例照片重新识别：无整页丢失；表格用量正确进入 materials；所有 µ/m 单位错误都有 warning。

## 结果

在本机 8080 端口的 GLM-OCR 上重新识别 5 张示例照片（单页单独发送）：

| | 旧流程 | 新流程 |
|---|---|---|
| 每页耗时 | 90–204 s，note 5 失败 | 约 5 s，全部成功 |
| 试剂表用量 | 多数填成分子量或当量 | 按 m / V / n / eq 正确归位 |
| µ/m 单位错误 | 无提示 | 9 处全部给出警告，无误报 |

已知限制：反应式（结构图）仍无法识别；被划掉的数值可能被读入（note 4 的 13 µL）；温度可能取自
第二步反应条件（note 1 的 60 °C）。这些都保留原文片段供人工核对。
