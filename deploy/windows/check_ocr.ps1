<#
.SYNOPSIS
    Diagnose the Windows/WSL prerequisites for DailyChem local OCR.
#>

$ErrorActionPreference = "Continue"
Write-Host "== Windows =="
Get-ComputerInfo -Property WindowsProductName,WindowsVersion,OsBuildNumber | Format-List
Write-Host "== NVIDIA =="
nvidia-smi.exe
Write-Host "== WSL status =="
wsl.exe --status
Write-Host "== WSL distributions =="
wsl.exe --list --verbose
Write-Host "== DailyChem OCR state =="
$statePath = Join-Path $env:LOCALAPPDATA "DailyChem\ocr-install-state.json"
if (Test-Path -LiteralPath $statePath) { Get-Content -Raw -LiteralPath $statePath } else { Write-Host "Installation state file was not found." }
