#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 <profile-dir>"
  exit 1
fi

PROFILE_DIR="$1"
STORE_REGISTRY="${PROFILE_DIR}/stores_registry.json"
SIGNAL_RULES="${PROFILE_DIR}/store_signal_rules.json"
SNAPSHOT_DIR="${PROFILE_DIR}/snapshots"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

FEISHU_ENABLED=0
if [ -n "${GBM_FEISHU_WEBHOOK:-}" ]; then
  FEISHU_ENABLED=1
  echo "feishu_push=enabled"
else
  echo "feishu_push=disabled(no_webhook)"
fi

export GBM_STORE_REGISTRY="$STORE_REGISTRY"
if [ -f "$SIGNAL_RULES" ]; then
  export GBM_SIGNAL_RULES="$SIGNAL_RULES"
fi

if [ -d "$SNAPSHOT_DIR" ]; then
  [ -f "${SNAPSHOT_DIR}/review_dianping.json" ] && export GBM_DIANGPING_FILE="${SNAPSHOT_DIR}/review_dianping.json"
  [ -f "${SNAPSHOT_DIR}/review_douyin.json" ] && export GBM_DOUYIN_FILE="${SNAPSHOT_DIR}/review_douyin.json"
  [ -f "${SNAPSHOT_DIR}/review_amap.json" ] && export GBM_AMAP_FILE="${SNAPSHOT_DIR}/review_amap.json"
  [ -f "${SNAPSHOT_DIR}/delivery_meituan.json" ] && export GBM_MEITUAN_FILE="${SNAPSHOT_DIR}/delivery_meituan.json"
  [ -f "${SNAPSHOT_DIR}/delivery_eleme.json" ] && export GBM_ELEME_FILE="${SNAPSHOT_DIR}/delivery_eleme.json"
  [ -f "${SNAPSHOT_DIR}/delivery_jdwm.json" ] && export GBM_JDWM_FILE="${SNAPSHOT_DIR}/delivery_jdwm.json"
fi

RUN_ARGS=(--mode all --no-notify)
if [ "$FEISHU_ENABLED" -eq 1 ]; then
  RUN_ARGS=(--mode all)
fi

PYTHONPATH=src python3 -m gb_monitor.cli init-db
READINESS_ARGS=(--profile-dir "$PROFILE_DIR")
if [ "$FEISHU_ENABLED" -eq 1 ]; then
  READINESS_ARGS+=(--require-feishu)
fi
PYTHONPATH=src python3 -m gb_monitor.cli profile-readiness "${READINESS_ARGS[@]}"
PYTHONPATH=src python3 -m gb_monitor.cli validate-registry --registry "$STORE_REGISTRY"
PYTHONPATH=src python3 -m gb_monitor.cli run "${RUN_ARGS[@]}"
PYTHONPATH=src python3 -m gb_monitor.cli report --hours 24
PYTHONPATH=src python3 -m gb_monitor.cli profile-deliverable \
  --profile-dir "$PROFILE_DIR" \
  --output "${PROFILE_DIR}/single_store_deliverable.md"

if [ -f "$SIGNAL_RULES" ]; then
  SIGNAL_ARGS=(
    --profile-dir "$PROFILE_DIR"
    --mode all
    --mark-dispatched
    --board-output "${PROFILE_DIR}/signal_watchboard.md"
    --report-output "${PROFILE_DIR}/signal_report.txt"
  )
  if [ "$FEISHU_ENABLED" -eq 1 ]; then
    SIGNAL_ARGS+=(--notify)
  fi

  SIGNAL_OUTPUT="$(PYTHONPATH=src python3 -m gb_monitor.cli profile-signals "${SIGNAL_ARGS[@]}")"
  printf '%s\n' "$SIGNAL_OUTPUT"
  if [ "$FEISHU_ENABLED" -eq 1 ] && ! printf '%s\n' "$SIGNAL_OUTPUT" | grep -q '^delivered=True$'; then
    echo "error=feishu_signal_delivery_failed" >&2
    exit 1
  fi
  PYTHONPATH=src python3 -m gb_monitor.cli profile-signal-deliverable \
    --profile-dir "$PROFILE_DIR" \
    --output "${PROFILE_DIR}/signal_delivery_explainer.md"
  PYTHONPATH=src python3 -m gb_monitor.cli profile-usage-guide \
    --profile-dir "$PROFILE_DIR" \
    --output "${PROFILE_DIR}/client_usage_guide.md"
fi
