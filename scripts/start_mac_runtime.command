#!/bin/bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_HOME="$HOME/GBM_Runtime/shibaojie"
LOG_FILE="$APP_HOME/startup.log"

mkdir -p "$APP_HOME"

if [ "$SOURCE_DIR" != "$APP_HOME" ]; then
  echo "[0/5] Preparing runtime folder..."
  rsync -a \
    --exclude ".venv" \
    --exclude "__pycache__" \
    --exclude ".git" \
    --exclude "*.zip" \
    "$SOURCE_DIR"/ "$APP_HOME"/
fi

cd "$APP_HOME"
{
  echo "start_time=$(date '+%F %T')"
  echo "app_home=$APP_HOME"
} > "$LOG_FILE"

echo "[1/5] Checking Python..."
if ! PYTHON_BIN="$("$SOURCE_DIR/scripts/resolve_python_macos.sh")"; then
  echo
  echo "Python 3.11+ with tkinter was not found on this Mac."
  echo "Please install official Python 3 for macOS first."
  echo "Download: https://www.python.org/downloads/macos/"
  echo "Log file: $LOG_FILE"
  echo
  read -r -p "按回车键关闭窗口..."
  exit 1
fi
echo "python=$PYTHON_BIN" >> "$LOG_FILE"

echo "[2/5] Checking tkinter..."
if ! "$PYTHON_BIN" -c "import tkinter" >> "$LOG_FILE" 2>&1; then
  echo
  echo "Python is installed, but tkinter is missing."
  echo "Please reinstall official Python 3 for macOS."
  echo "Log file: $LOG_FILE"
  echo
  read -r -p "按回车键关闭窗口..."
  exit 1
fi

if [ ! -f ".env" ]; then
  echo "[3/5] Creating local config..."
  cp ".env.example" ".env"
fi

mkdir -p auth
echo "[4/5] Preparing login folder..."
echo "auth_dir=$APP_HOME/auth" >> "$LOG_FILE"

echo "[5/5] Launching control center..."
export PYTHONPATH=src
exec "$PYTHON_BIN" -m gb_monitor.control_center \
  --root-dir "$APP_HOME" \
  --profile-dir "$APP_HOME/data/client_profiles/shibaojie" \
  --env-file "$APP_HOME/.env" \
  --rules-file "$APP_HOME/data/client_profiles/shibaojie/store_signal_rules.json" \
  >> "$LOG_FILE" 2>&1
