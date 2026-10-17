# DailyChem

DailyChem 是面向日常化学工作流的本地辅助工具，用于整理化合物结构、谱学数据、实验记录和
项目归档。所有 assignment 与 AI 输出都保留人工复核要求，不会自动覆盖原始实验数据。

## 主要功能

- 读取 SMILES、MOL、SDF、CDX 和 CDXML，并生成结构信息与带原子编号的图片。
- 解析 MestReNova NMR multiplet table，生成 publication-style NMR 文本。
- 计算和格式化 HRMS，并整理 IR、UV-vis 表征文本。
- 根据 YAML/JSON 生成中英文实验记录草稿。
- 生成 1H/13C NMR candidate assignment 与一致性警告。
- 创建标准 compound 归档、备份和本地 SQLite 历史检索。
- 使用 OpenAI Agents SDK 生成带 warnings 的可复核草稿。
- 拍摄或上传手写实验记录照片，通过本地 WSL2 + vLLM + GLM-OCR 生成可校对的实验记录草稿。

## 安装

需要 Python 3.11 或更高版本，以及 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync
```

首次使用照片 OCR 时，Windows 用户需要以管理员身份运行
[`deploy/windows/install_ocr.ps1`](deploy/windows/install_ocr.ps1)。安装器会引导完成 WSL2、Ubuntu、
vLLM 和 GLM-OCR 配置；首次启用 WSL2 可能需要重启。照片和识别结果始终留在本机。

## 启动图形界面

Windows 用户可双击 `run.bat`，Mac/Linux 用户运行：

```bash
bash run.sh
```

也可以直接运行：

```bash
uv run streamlit run app.py
```

浏览器通常会自动打开；项目默认地址是 `http://localhost:8620`。

## 命令行

查看全部命令：

```bash
uv run chemwf --help
```

常用示例：

```bash
uv run chemwf nmr format examples/raw/nmr_multiplet_table_clean_example.tsv --frequency 400 --solvent CDCl3
uv run chemwf records generate examples/raw/experiment_record_example.yaml --language zh
uv run chemwf ms hrms --smiles "CCOC(=O)c1ccccc1" --adduct "[M+Na]+"
```

## 使用文档

- [完整使用指南](docs/user_guide.md)
- [图形界面逐页说明](docs/ui_usage.md)
- [常见问题](docs/faq.md)

## 数据安全

- 默认不覆盖已有 compound 归档。
- 备份与归档只读取源文件，并把结果写到独立位置。
- LLM/Agent 输出始终是 draft，必须人工复核。
- API key 只从环境变量或本地 `.env` 读取，不写入输出、配置或日志。
