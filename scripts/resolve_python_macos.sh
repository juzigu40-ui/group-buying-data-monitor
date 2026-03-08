#!/usr/bin/env bash
set -euo pipefail

check_candidate() {
  local candidate="$1"
  [ -x "$candidate" ] || return 1
  "$candidate" - <<'PY' >/dev/null 2>&1
import sys
import tkinter
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
}

for candidate in \
  "/opt/homebrew/bin/python3.13" \
  "/usr/local/bin/python3.13" \
  "/opt/homebrew/bin/python3.12" \
  "/usr/local/bin/python3.12" \
  "/opt/homebrew/bin/python3.11" \
  "/usr/local/bin/python3.11" \
  "$(command -v python3.13 2>/dev/null || true)" \
  "$(command -v python3.12 2>/dev/null || true)" \
  "$(command -v python3.11 2>/dev/null || true)" \
  "$(command -v python3 2>/dev/null || true)"
do
  [ -n "$candidate" ] || continue
  if check_candidate "$candidate"; then
    printf '%s\n' "$candidate"
    exit 0
  fi
done

exit 1
