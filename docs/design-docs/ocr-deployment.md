# 本地 GLM-OCR 部署说明

DailyChem 的照片 OCR 使用 Windows 本地应用调用 WSL2 内的 vLLM/GLM-OCR，不依赖云端 OCR。

## 一次性安装

目标机器需要 Windows 10/11 22H2 或更高版本、管理员权限、联网、硬件虚拟化和支持 WSL CUDA 的 NVIDIA 驱动。
正式支持路径是 NVIDIA RTX 5090。

在项目根目录以管理员身份打开 PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy\windows\install_ocr.ps1
```

脚本会安装或检查 WSL2、Ubuntu 24.04、Python 3.12、uv 和 vLLM 0.31.0，并从官方
[`zai-org/GLM-OCR`](https://huggingface.co/zai-org/GLM-OCR/tree/main) 下载模型。安装状态写入
`%LOCALAPPDATA%\DailyChem\ocr-install-state.json`，日志写入 `%LOCALAPPDATA%\DailyChem\logs\`。

Torch 不再固定为旧版本；安装器让 vLLM 0.31.0 的依赖解析器选择兼容版本，以避免 RTX 5090、CUDA
和 vLLM 之间出现不匹配。若需要企业环境的完全锁定版本，可把 `ocr-manifest.json` 中的
`torch_version` 从 `auto` 改成经过验证的具体版本。
首次启用 WSL2 或 Ubuntu 时可能需要重启；重启后重新执行脚本即可恢复。

模型 revision 可以通过 `-ModelRevision` 固定：

```powershell
.\deploy\windows\install_ocr.ps1 -ModelRevision <tested-revision>
```

实际部署前应将经过 RTX 5090 验证的 revision 写入 `deploy/windows/ocr-manifest.json`。

## 运行方式

启动 DailyChem 后，在 Experiment Record 页面上传照片并点击 **识别照片**。应用会检查
`http://127.0.0.1:8000/v1/models`，服务未运行时通过 `wsl.exe` 按需启动 vLLM。服务日志在 WSL 的
`~/dailychem-ocr/vllm.log`。

命令行诊断：

```bash
uv run chemwf ocr doctor
uv run chemwf ocr status
uv run chemwf ocr start
uv run chemwf ocr stop
```

## 故障排查

- `找不到 wsl.exe`：先在 Windows 功能中启用 WSL，并重启后重新执行安装脚本。
- `CUDA unavailable in WSL`：更新 NVIDIA 驱动，确认 `nvidia-smi` 能在 Windows 工作，再运行
  `wsl --update`。
- 模型服务启动超时：查看 WSL 的 `~/dailychem-ocr/vllm.log`，确认模型已经下载且显存足够。
- OCR 返回非法 JSON：保留原始响应，先检查模型 revision 和 vLLM 版本是否与 manifest 一致。

照片、原始 OCR 响应和结构化草稿只会在用户勾选项目归档选项时写入 compound 的 `ocr/` 目录。
