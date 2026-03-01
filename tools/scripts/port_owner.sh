#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-}"
if [[ -z "$PORT" ]]; then
  exit 0
fi

LINE="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $2}' || true)"
if [[ -z "$LINE" ]]; then
  exit 0
fi

PID="$LINE"
CMD="$(ps -p "$PID" -o command= 2>/dev/null | sed -E 's/^[[:space:]]+//' || true)"
printf '%s|%s\n' "$PID" "$CMD"
