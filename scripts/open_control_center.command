#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"
if [ -f ".venv/bin/python" ]; then
  export PYTHONPATH=src
  exec ".venv/bin/python" -m gb_monitor.control_center \
    --root-dir "$REPO_DIR" \
    --profile-dir "data/client_profiles/shibaojie" \
    --env-file ".env" \
    --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
fi

export PYTHONPATH=src
exec python3 -m gb_monitor.control_center \
  --root-dir "$REPO_DIR" \
  --profile-dir "data/client_profiles/shibaojie" \
  --env-file ".env" \
  --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
