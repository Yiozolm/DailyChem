# 常见问题（FAQ）

## 安装与运行

**Q: `uv sync` 报错 / 装不上？**
确认已安装 uv（见 [uv 官网](https://docs.astral.sh/uv/)）和 Python ≥ 3.11。
首次 `uv sync` 会下载 RDKit 等较大依赖，需要联网，耐心等待。

**Q: 双击 `run.bat` / `bash run.sh` 后浏览器没自动打开？**
看终端输出的本地地址，手动在浏览器打开，通常是 `http://localhost:8501`。

## 结构输入

**Q: ChemDraw 的 `.cdx` 打不开 / 报不支持？**
本工具用 RDKit 原生解析 `.cdx` / `.cdxml`。极少数环境下 RDKit 构建不含 ChemDraw 支持，
此时按提示在 ChemDraw 里把分子另存为 `.mol` 或 `.sdf` 再上传即可。
合成路线 / 多分子文件请单独导出目标分子。

## NMR

**Q: 19F / 31P 谱能用吗？**
能。publication-style 文本格式化已支持 1H / 13C / 19F / 31P 四种核。assignment 候选归属
目前覆盖 1H / 13C；19F / 31P 的区间归属规则后续再加。

**Q: 怎么快速判断「谱对不对得上结构」？**
用 NMR Assignment 页（或 `chemwf nmr check`）。程序用 RDKit 对称性数出结构理论上应有几个
**唯一信号**，与你的实测峰数对比：一致 = OK；实测偏多可能有杂质 / 旋转异构 / 对称性偏低；
实测偏少可能信号重叠或漏峰。注意它只比对**信号数**，不预测化学位移数值。

**Q: 我粘贴的 multiplet 表解析出来氢数 / J 值很奇怪？**
工具**忠实解析**你给的表格，不替你做化学合理性判断（比如杂质峰被并入同一 multiplet）。
请回到 MestReNova 检查积分区间，或在 Assignment 页看风险提示。

## MS / HRMS

**Q: HRMS 支持哪些 adduct？**
当前支持单电荷常见集合：`[M+H]+`、`[M+Na]+`、`[M+K]+`、`[M+NH4]+`、`[M-H]-`、`[M+H-H2O]+`。
多电荷 / 多聚体 / 同位素分布暂不支持。

**Q: ppm 误差怎么算的？**
`(found − calc) / calc × 1e6`，保留符号（实测偏高为正、偏低为负），保留 1 位小数。

## LLM 辅助

**Q: 用 LLM 润色 / 摘要需要什么？**
需要一个 OpenAI（或兼容）API key。在项目根目录建 `.env`，写
`OPENAI_API_KEY=...`（DeepSeek 用 `DEEPSEEK_API_KEY`）。API key 只从环境变量 / `.env` 读取，
不会写进配置或日志。详见 `docs/exec-plans/completed/phase9_openai_sdk_plan.md`。

**Q: LLM 会不会编造数据？**
prompt 和后处理都禁止新增表征数值；输出恒为 draft 且带 warnings。即便如此，
**所有 LLM 输出都必须人工核对**后才能用作最终结论或论文 SI。

## 数据与历史库

**Q: 历史数据库在哪？会上传吗？**
默认 `data/chem_workflow.sqlite`，纯本地，不随 git 提交（已在 `.gitignore`）。
可在 History Search 页或 `.chemwf.toml` 改路径。

**Q: 会覆盖我的原始数据吗？**
不会。归档 / 备份都只读源文件，新文件写到单独位置；重复初始化默认不覆盖，需显式 `--overwrite`。
`chemwf backup --id <ID>` 可把某化合物文件夹打包到 `backups/`。

## 配置

**Q: 怎么改默认频率 / 溶剂 / adduct？**
运行 `uv run chemwf config init` 在当前目录生成 `.chemwf.toml`，编辑后图形界面默认值就会跟着变。
`uv run chemwf config show` 查看当前生效配置。

## 范围

**Q: 能不能直接 AI 自动解谱 / 从谱图图片识别？**
不能，也刻意不做。自动解谱目前不可靠，本工具定位是**半自动、可解释、可人工确认**的辅助，
不从图像反推 peak list，不给唯一 assignment 定论。

**Q: 有独立 exe 安装包吗？**
暂无。目前通过 `uv sync` + `run.sh` / `run.bat` 运行；独立可执行包体积大、跨平台维护成本高，留待后续。
