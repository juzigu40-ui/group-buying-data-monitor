#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 <profile-dir>"
  exit 1
fi

PROFILE_DIR="$1"
STORE_REGISTRY="${PROFILE_DIR}/stores_registry.json"
SIGNAL_RULES="${PROFILE_DIR}/store_signal_rules.json"
SIGNAL_INPUT="${PROFILE_DIR}/douyin_signal_candidates.json"
SNAPSHOT_DIR="${PROFILE_DIR}/snapshots"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
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

PYTHONPATH=src python3 -m gb_monitor.cli init-db
PYTHONPATH=src python3 -m gb_monitor.cli validate-registry --registry "$STORE_REGISTRY"
PYTHONPATH=src python3 -m gb_monitor.cli run --mode all --no-notify
PYTHONPATH=src python3 -m gb_monitor.cli report --hours 24

if [ -f "$SIGNAL_INPUT" ] && [ -f "$SIGNAL_RULES" ]; then
  PYTHONPATH=src python3 -m gb_monitor.cli score-signals \
    --input "$SIGNAL_INPUT" \
    --rules "$SIGNAL_RULES"
fi
