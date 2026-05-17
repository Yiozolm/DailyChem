# NMR 输入策略备忘

> 配套 `docs/exec-plans/active/chem_ai_workflow_todo.md` Phase 0 验收里 NMR 输入决策。
> 调研日期：2026-05-17。

## 背景

化学同学的 NMR 工作流是：

```
Bruker 仪器（TopSpin） → fid 等原始文件 → MestReNova 处理（FT/相位/基线/peak picking/积分）
  → 解析谱（含化学位移标签 + 积分数据）→ 论文 SI 里的描述文本
```

设计阶段同学提供了三类样例文件，对应工作流的三个层级：

1. `data/raw/数据目录.jpg` —— Bruker TopSpin 数据文件夹（`fid`、`acqus`、`pdata/` 等）
2. `data/raw/原始谱.jpg` —— MestReNova 里傅里叶变换后的频域谱，未做 peak picking
3. `data/raw/解析谱.jpg` —— MestReNova 完整解析后（化学位移、积分、multiplet 标签）

## 决策：第一版接 MestReNova 解析后的 peak table（结构化导出）

| 选项 | 是否采用 | 理由 |
|---|---|---|
| Bruker 仪器原始数据目录（fid 等） | ❌ | 处理这层等于在项目里重建 MestReNova 的 FT/相位/基线/peak picking 全管线；与"减少琐事"目标背道而驰。Phase 0 也明确"不接仪器原始数据"。 |
| 谱图截图（jpg/png） | ❌ | 需要 OCR / 图像反推峰位置，精度受像素分辨率限制，且会丢掉同学已经做完的积分数据。"重做一遍同学已经做完的事"。 |
| **MestReNova peak table 结构化导出** | ✅ | 同学的现有工作流已经产出了所有需要的结构化字段（shift / integration / multiplicity / J / assignment）；我们只需读取并标准化。不改变同学的操作习惯。 |

## 期望的输入格式（待同学确认导出选项）

**首选**：MestReNova `File → Save As → Peak List CSV`，包含以下列（不区分大小写）：

```
shift_ppm    integration    multiplicity    j_hz    assignment    note
```

**备选**：右键 Multiplet Manager → Copy Multiplet Report → 贴成 `.txt`。第一版可以先支持 CSV，文本报告 parser 留作 P1。

## 已知的处理细节（来自 `data/raw/解析谱.jpg`）

观察到 MestReNova 的几个习惯，Phase 3 数据模型需要兼容：

1. **积分基准是相对的**：解析谱里 A 峰（3.11 ppm，CH₂）被设为 1.00H，其他峰是相对值（B=0.22, C=0.17, D=1.00, E=0.17, F=0.18）。Phase 4 生成最终 NMR 描述时需要支持"重新设积分参考 + 取整到结构氢数"。
2. **multiplet 标签用字母编号**（A/B/C/D/E/F）：peak table 里 `assignment` 列可能放的是 `A` 这种内部 ID，而不是 `H-3` 这种结构原子编号。Phase 8 assignment 辅助要做"MestReNova 字母 → 结构原子编号"的映射。
3. **嵌入了结构图**：MestReNova 可以在谱图旁边嵌结构图。这部分信息我们用自己的 `chemwf structure draw` 重新生成即可，不依赖 MestReNova 嵌图。

## 待同学确认的事项

- [ ] MestReNova 是否能直接导出 `File → Save As → Peak List CSV`？字段命名与上面假设是否一致？
- [ ] 一份脱敏 CSV 样例（最好和 `data/raw/解析谱.jpg` 是同一谱），用来开 Phase 3 parser
- [ ] 同一化合物的 13C NMR peak list 一份，确认 1H/13C 表头是否一致

## 影响范围

- **Phase 3**（NMR peak list 数据模型与解析）：等同学提供脱敏 CSV 后开工；不再考虑接受谱图截图或仪器原始数据。
- **Phase 4**（标准 NMR 描述自动生成）：积分归一化策略需要支持"以某峰为参考重新缩放"。
- **Phase 8**（结构—谱图 assignment 辅助）：MestReNova multiplet 字母 ID ↔ 结构原子编号的映射是关键 UX。

## 现实校正（2026-05-17 实施 Phase 3 时）

原先假定同学走 `File → Save As → Peak List CSV` 给一份字段命名规整的 CSV。实际同学不熟悉这个路径，给出的样例是：

1. `data/raw/H-NMR.txt` —— MestReNova Peak Picking 导出（只有 shift + intensity，缺 multiplicity / integration / J），**信息量不够，第一版不接**
2. multiplet 表 **直接复制粘贴**的 tab-separated 文本（`View → Tables → Multiplets` 选中表格 Ctrl+C），字段含 Name / Shift / Range / H's / Integral / Class / J's —— **第一版主输入格式**

### multiplet 表两种复制粘贴姿态

同学的实际复制粘贴行为有两种，第一版 parser 都支持：

**姿态 A：tab-separated**（贴到识别 tab 的地方，如纯文本编辑器 / 命令行）

```
Name	Shift	Range	H's	Integral	Class	J's
1	F (s)	8.56	8.86 .. 8.29	1	1.06	s
2	E (s)	7.50	7.80 .. 7.23	1	1.00	s
3	D (d)	3.23	3.64 .. 3.05	45	45.13	d	97.06
```

**姿态 B：newline-separated**（贴到不识别 tab 的输入框，如微信、某些 web 表单，tab 被换行替换）

```
Name
Shift
Range
H's
Integral
Class
J's
1
F (s)
8.56
8.72 .. 8.34
0
0.18
s

2
E (s)
...
```

Parser 自动检测姿态 B（第一非空行不含 tab 且匹配列名别名），把它 normalize 成姿态 A 后走同一套解析逻辑。表头识别按"连续列名行"，数据组按"空行分隔"。

### 列名 / 字段语法约定

### 列名 / 字段语法约定

- 列分隔符：**Tab**（姿态 A）或 **newline**（姿态 B，自动 normalize）
- 列名大小写不敏感、允许常见别名（`H's` / `H` / `H count`、`Class` / `Multiplicity` 等）
- `Range`：`high .. low` 或 `high–low`，parser 自动归一成 `(low, high)`
- `J's`：单值或多值用任意非数字字符分隔，"J = 8.0 Hz" / "J1 = 8.0, J2 = 2.0 Hz" 都接受
- **复制粘贴 quirk**：MestReNova 表里第一列是行号但表头不带列名。Parser 自动检测两种情况：
  - 数据行恰好多 1 列且首字段是纯数字 → 丢首列
  - 数据行与表头等列、首字段是纯数字、表头第一列名不是 Shift 别名 → 表头前补一个虚 `#` 列
- 单峰行末尾 `J's` 列为空被吞 → parser 自动 pad 空串

### JACS 文本格式（`parse_inline_report`）暂不做

`Scripts → Report → Multiplets → JACS` 走的路径是直接出 "1H NMR (400 MHz, CDCl₃) δ 7.26 (d, J = 8.0 Hz, 2H), ..."。这条路径同学也能用，但 multiplet 表的列式数据更结构化（字段直接对齐、不依赖正则），所以**第一版只做 multiplet 表 parser**，JACS 文本格式留作后续 P1。

### 给同学的导出指南

待 Phase 3 完成后落到 `docs/references/mestrenova-export-multiplet.md`（包含：`View → Tables → Multiplets` 操作、复制粘贴步骤、积分归一化提醒、杂质峰处理）。

