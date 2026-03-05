#!/usr/bin/env bash
set -euo pipefail

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PYTHONPATH=src python -m gb_monitor.cli init-db
PYTHONPATH=src python -m gb_monitor.cli run --mode all --no-notify
PYTHONPATH=src python -m gb_monitor.cli report --hours 24
