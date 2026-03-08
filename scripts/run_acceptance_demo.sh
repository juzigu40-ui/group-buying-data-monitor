#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 <profile-dir> [--require-feishu]"
  exit 1
fi

PROFILE_DIR="$1"
REQUIRE_FEISHU=0
if [ "${2:-}" = "--require-feishu" ]; then
  REQUIRE_FEISHU=1
fi

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if ! PYTHON_BIN="$(./scripts/resolve_python_macos.sh)"; then
  echo "acceptance_ready=False"
  echo "error=missing_python311_with_tkinter"
  exit 1
fi

echo "acceptance_step=readiness_check"
READINESS_ARGS=(--profile-dir "$PROFILE_DIR")
if [ "$REQUIRE_FEISHU" -eq 1 ]; then
  READINESS_ARGS+=(--require-feishu)
fi
PYTHONPATH=src "$PYTHON_BIN" -m gb_monitor.cli profile-readiness "${READINESS_ARGS[@]}"

if [ "$REQUIRE_FEISHU" -eq 1 ]; then
  echo "acceptance_step=feishu_ping"
  PYTHONPATH=src "$PYTHON_BIN" -m gb_monitor.cli feishu-ping
fi

echo "acceptance_step=full_run"
./scripts/run_profile.sh "$PROFILE_DIR"

REQUIRED_OUTPUTS=(
  "${PROFILE_DIR}/single_store_deliverable.md"
  "${PROFILE_DIR}/signal_watchboard.md"
  "${PROFILE_DIR}/signal_report.txt"
  "${PROFILE_DIR}/signal_delivery_explainer.md"
  "${PROFILE_DIR}/client_usage_guide.md"
)

for path in "${REQUIRED_OUTPUTS[@]}"; do
  if [ ! -f "$path" ]; then
    echo "acceptance_ready=False"
    echo "missing_output=$path"
    exit 1
  fi
done

echo "acceptance_ready=True"
echo "generated_outputs=${REQUIRED_OUTPUTS[*]}"
echo "check_result=readiness_ok + full_run_ok"
if [ "$REQUIRE_FEISHU" -eq 1 ]; then
  echo "check_result=feishu_ping_ok + readiness_ok + full_run_ok"
fi
