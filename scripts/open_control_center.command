#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"
if ! PYTHON_BIN="$(./scripts/resolve_python_macos.sh)"; then
  echo
  echo "Python 3.11+ with tkinter was not found on this Mac."
  echo "Please install official Python 3 for macOS first."
  echo "Download: https://www.python.org/downloads/macos/"
  echo
  read -r -p "按回车键关闭窗口..."
  exit 1
fi

export PYTHONPATH=src
exec "$PYTHON_BIN" -m gb_monitor.control_center \
  --root-dir "$REPO_DIR" \
  --profile-dir "data/client_profiles/shibaojie" \
  --env-file ".env" \
  --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
