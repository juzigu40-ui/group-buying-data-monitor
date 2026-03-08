#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"
./scripts/install_local.sh

echo
echo "下一步：双击 scripts/open_common_settings.command 填飞书 webhook 和时间段。"
read -r -p "按回车键关闭窗口..."
