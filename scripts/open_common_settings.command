#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
fi

echo "将打开两个文件："
echo "1. .env（填飞书 webhook，改时间段/抓取频率）"
echo "2. store_signal_rules.json（改门店 KPI 目标）"

open -a TextEdit "$REPO_DIR/.env"
open -a TextEdit "$REPO_DIR/data/client_profiles/shibaojie/store_signal_rules.json"

echo
echo "建议只先改这几个地方："
echo "- GBM_FEISHU_WEBHOOK"
echo "- GBM_SIGNAL_WINDOW_START / GBM_SIGNAL_WINDOW_END / GBM_SIGNAL_INTERVAL_MINUTES"
echo "- daily_target_count"
read -r -p "文件已打开，按回车键关闭窗口..."
