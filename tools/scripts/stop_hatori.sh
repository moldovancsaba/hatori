#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-all}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UI_PORT="${PORT:-8093}"
API_PORT_VAL="${API_PORT:-8094}"

stop_port() {
  local port="$1"
  local kind="$2"
  local pid
  pid="$(${ROOT_DIR}/tools/scripts/port_owner.sh "$port" | sed -n 's/^PID=\([0-9][0-9]*\).*/\1/p')"

  if [ -z "$pid" ]; then
    echo "[${kind}] not running on port ${port}"
    return 0
  fi

  if ! "${ROOT_DIR}/tools/scripts/is_hatori_process.sh" "$pid"; then
    local cmd
    cmd="$(ps -p "$pid" -o command= 2>/dev/null | sed 's/^[[:space:]]*//' || true)"
    echo "[${kind}] skip non-Hatori pid=${pid} cmd=${cmd}"
    return 0
  fi

  echo "[${kind}] stopping pid=${pid} on port ${port}"
  kill -TERM "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "[${kind}] stopped"
      return 0
    fi
    sleep 0.2
  done
  echo "[${kind}] TERM timeout; sending KILL to pid=${pid}"
  kill -KILL "$pid" 2>/dev/null || true
}

case "$TARGET" in
  ui)
    stop_port "$UI_PORT" "ui"
    ;;
  api)
    stop_port "$API_PORT_VAL" "api"
    ;;
  all)
    stop_port "$UI_PORT" "ui"
    stop_port "$API_PORT_VAL" "api"
    ;;
  *)
    echo "usage: $0 [ui|api|all]" >&2
    exit 2
    ;;
esac
