#!/usr/bin/env bash
set -euo pipefail

# Always run from the project root, even when this script is launched elsewhere.
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "未检测到 uv。请先安装 uv："
  echo "https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

echo "正在启动 DailyChem 图形界面..."
echo "如果浏览器没有自动打开，请访问终端里显示的本地地址。"

uv run streamlit run app.py "$@"
