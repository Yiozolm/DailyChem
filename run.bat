@echo off
setlocal

rem Always run from the project root, even when this script is double-clicked.
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv was not found.
    echo Please install uv first:
    echo https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

echo Starting DailyChem web UI...
echo If the browser does not open automatically, use the local URL shown below.

uv run streamlit run app.py %*

if errorlevel 1 (
    echo.
    echo DailyChem exited with an error.
    pause
    exit /b 1
)

endlocal
