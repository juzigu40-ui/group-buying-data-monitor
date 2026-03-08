#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "install_ready=False"
  echo "error=missing_python3"
  exit 1
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  echo "venv_created=.venv"
else
  echo "venv_exists=.venv"
fi

source .venv/bin/activate
python -m pip install -U pip >/dev/null 2>&1
pip install -e .

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "env_created=.env"
else
  echo "env_exists=.env"
fi

echo "install_ready=True"
echo "next_step=edit_.env_then_run_acceptance_demo"
