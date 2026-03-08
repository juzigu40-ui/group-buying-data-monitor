#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"
./scripts/run_acceptance_demo.sh data/client_profiles/shibaojie --require-feishu

echo
echo "验收已执行。请检查飞书消息和生成的交付文件。"
read -r -p "按回车键关闭窗口..."
