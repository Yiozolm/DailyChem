<#
.SYNOPSIS
    Install the local DailyChem GLM-OCR runtime in WSL2.

.DESCRIPTION
    The script is intentionally resumable. It checks Windows/WSL/GPU prerequisites, installs
    Ubuntu 24.04 when needed, creates a uv-managed Python environment, installs pinned runtime
    packages, and downloads the model into the WSL user's Hugging Face cache.

    A first-time WSL installation may require a reboot. The script exits with code 3010 after
    printing the next step; running it again resumes from the existing state.
#>

[CmdletBinding()]
param(
    [string]$Distro = "Ubuntu-24.04",
    [string]$ModelId = "zai-org/GLM-OCR",
    [string]$ModelRevision = "",
    [switch]$SkipModelDownload
)

$ErrorActionPreference = "Stop"
$ManifestPath = Join-Path $PSScriptRoot "ocr-manifest.json"
$StateRoot = Join-Path $env:LOCALAPPDATA "DailyChem"
$StatePath = Join-Path $StateRoot "ocr-install-state.json"
$LogPath = Join-Path $StateRoot "logs\ocr-install.log"
$null = New-Item -ItemType Directory -Force -Path $StateRoot, (Split-Path $LogPath -Parent)

function Write-Step([string]$Message) {
    $line = "[$(Get-Date -Format s)] $Message"
    Write-Host $line
    Add-Content -LiteralPath $LogPath -Value $line
}

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Wsl([string]$Command) {
    Write-Step "WSL: $Command"
    & wsl.exe -d $Distro -- bash -lc $Command
    if ($LASTEXITCODE -ne 0) { throw "WSL command failed with exit code $LASTEXITCODE" }
}

if (-not (Test-Administrator)) {
    Write-Host "Requesting administrator privileges..."
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-Distro", "`"$Distro`"",
        "-ModelId", "`"$ModelId`""
    )
    if ($ModelRevision) { $arguments += @("-ModelRevision", "`"$ModelRevision`"") }
    if ($SkipModelDownload) { $arguments += "-SkipModelDownload" }
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments | Out-Null
    exit 0
}
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    Fail "wsl.exe was not found. Enable Windows virtualization and run wsl --install, then reboot."
}
if (-not (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)) {
    Fail "NVIDIA driver was not found. Install a WSL CUDA compatible driver and retry."
}

$manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
if (-not $ModelRevision -and $manifest.model_revision) { $ModelRevision = [string]$manifest.model_revision }
$modelVersionText = if ($ModelRevision) { "revision $ModelRevision" } else { "default revision" }
Write-Step "DailyChem GLM-OCR installation started: $ModelId ($modelVersionText)"

$wslStatus = (& wsl.exe --status 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $wslStatus -match "not installed|not enabled") {
    Write-Step "WSL2 is not ready. Running wsl --install; reboot and run this script again."
    & wsl.exe --install --no-distribution
    if ($LASTEXITCODE -ne 0) { Fail "WSL2 installation failed. Check Windows optional features and virtualization." }
    Write-Host "WSL2 installation requested. Reboot Windows and run this script again."
    exit 3010
}

$distros = (& wsl.exe --list --quiet 2>&1 | Out-String)
if ($distros -notmatch [regex]::Escape($Distro)) {
    Write-Step "Installing WSL distribution $Distro. The first launch may ask for a Linux user."
    & wsl.exe --install -d $Distro
    if ($LASTEXITCODE -ne 0) { Fail "Ubuntu installation failed. Run wsl --list --online to inspect available distributions." }
    Write-Host "Ubuntu installation requested. Complete first-user setup and run this script again."
    exit 3010
}

$gpu = (& nvidia-smi.exe --query-gpu=name --format=csv,noheader 2>&1 | Out-String).Trim()
if (-not $gpu) { Fail "NVIDIA did not report a GPU. Confirm the RTX 5090 driver supports WSL2." }
Write-Step "Windows GPU: $gpu"

try {
    Invoke-Wsl "sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip curl git ca-certificates"
    Invoke-Wsl "if ! command -v uv >/dev/null 2>&1; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi"
    Invoke-Wsl "export PATH=`$HOME/.local/bin:`$PATH; uv venv --python $($manifest.python_version) ~/dailychem-ocr/.venv"
    $torchSpec = if ($manifest.torch_version -and $manifest.torch_version -ne "auto") {
        "torch==$($manifest.torch_version)"
    } else {
        ""
    }
    Invoke-Wsl "export PATH=`$HOME/.local/bin:`$PATH; uv pip install --python ~/dailychem-ocr/.venv/bin/python $torchSpec vllm==$($manifest.vllm_version) huggingface_hub"
    if (-not $SkipModelDownload) {
        $revisionArg = if ($ModelRevision) { "--revision '$ModelRevision'" } else { "" }
        Invoke-Wsl "export PATH=`$HOME/.local/bin:`$PATH; ~/dailychem-ocr/.venv/bin/huggingface-cli download '$ModelId' $revisionArg --local-dir $($manifest.model_dir)"
    }
    Invoke-Wsl '~/dailychem-ocr/.venv/bin/python -c "import torch; assert torch.cuda.is_available(), ''CUDA unavailable in WSL''; print(torch.cuda.get_device_name(0))"'
    $state = [ordered]@{
        status = "ready"
        distro = $Distro
        model_id = $ModelId
        model_revision = if ($ModelRevision) { $ModelRevision } else { $null }
        installed_at = (Get-Date).ToUniversalTime().ToString("o")
        gpu = $gpu
    }
    $state | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding UTF8
    Write-Step "Installation complete. Run photo OCR in DailyChem or execute chemwf ocr status."
} catch {
    $state = [ordered]@{ status = "error"; message = $_.Exception.Message; updated_at = (Get-Date).ToUniversalTime().ToString("o") }
    $state | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding UTF8
    Fail $_.Exception.Message
}
