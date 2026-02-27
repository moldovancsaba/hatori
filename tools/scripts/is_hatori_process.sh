#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "" ]; then
  echo "usage: $0 PID" >&2
  exit 2
fi

PID="$1"
UI_PORT="${PORT:-8093}"
API_PORT_VAL="${API_PORT:-8094}"

cmd="$(ps -p "$PID" -o command= 2>/dev/null | sed 's/^[[:space:]]*//' || true)"
if [ -z "$cmd" ]; then
  exit 1
fi

case "$cmd" in
  *"uvicorn ui.app:app"*"--port ${UI_PORT}"*) exit 0 ;;
  *"-m uvicorn ui.app:app"*"--port ${UI_PORT}"*) exit 0 ;;
  *"uvicorn api.app:app"*"--port ${API_PORT_VAL}"*) exit 0 ;;
  *"-m uvicorn api.app:app"*"--port ${API_PORT_VAL}"*) exit 0 ;;
  *) exit 1 ;;
esac
