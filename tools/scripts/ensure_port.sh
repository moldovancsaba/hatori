#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "usage: $0 PORT KIND START_CMD" >&2
  exit 2
fi

PORT="$1"
KIND="$2"
START_CMD="$3"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

owner="$(${ROOT_DIR}/tools/scripts/port_owner.sh "$PORT")"
if [ "$owner" = "FREE" ]; then
  echo "[${KIND}] port ${PORT} is free, starting"
  exec bash -lc "$START_CMD"
fi

pid="$(printf '%s\n' "$owner" | sed -n 's/^PID=\([0-9][0-9]*\).*/\1/p')"
cmd="$(printf '%s\n' "$owner" | sed -n 's/^PID=[0-9][0-9]* CMD=//p')"

if [ -n "$pid" ] && "${ROOT_DIR}/tools/scripts/is_hatori_process.sh" "$pid"; then
  echo "[${KIND}] already running on port ${PORT} (pid=${pid})"
  if [ "$KIND" = "ui" ]; then
    echo "[ui] open http://127.0.0.1:${PORT}/chat"
  else
    echo "[api] endpoint http://127.0.0.1:${PORT}/v1/health"
  fi
  exit 0
fi

echo "[${KIND}] FAIL: port ${PORT} is in use by non-Hatori process" >&2
echo "PID=${pid:-unknown}" >&2
echo "CMD=${cmd:-unknown}" >&2
if [ "$KIND" = "api" ]; then
  echo "Use API_PORT=<free-port> for temporary debugging." >&2
else
  echo "Use PORT=<free-port> for temporary debugging." >&2
fi
exit 1
