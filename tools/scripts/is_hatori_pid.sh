#!/usr/bin/env bash
set -euo pipefail

PID="${1:-}"
ROOT="${2:-}"
if [[ -z "$PID" ]]; then
  exit 1
fi

CMD="$(ps -p "$PID" -o command= 2>/dev/null | sed -E 's/^[[:space:]]+//' || true)"
if [[ -z "$CMD" ]]; then
  exit 1
fi

if [[ -n "$ROOT" && "$CMD" == *"$ROOT"* ]]; then
  exit 0
fi
if [[ "$CMD" == *"uvicorn api.app:app"* || "$CMD" == *"uvicorn ui.app:app"* ]]; then
  exit 0
fi

exit 1
