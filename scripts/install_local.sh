#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! PYTHON_BIN="$(./scripts/resolve_python_macos.sh)"; then
  echo "install_ready=False"
  echo "error=missing_python311_with_tkinter"
  exit 1
fi

echo "python_bin=$PYTHON_BIN"

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "env_created=.env"
else
  echo "env_exists=.env"
fi

mkdir -p auth
echo "auth_dir=auth"

echo "install_ready=True"
echo "next_step=edit_.env_then_run_acceptance_demo"
