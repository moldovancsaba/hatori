#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "" ]; then
  echo "usage: $0 PORT" >&2
  exit 2
fi

PORT="$1"

pid="$(lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN -Fp 2>/dev/null | sed -n 's/^p//p' | head -n1 || true)"

if [ -z "$pid" ]; then
  echo "FREE"
  exit 0
fi

cmd="$(ps -p "$pid" -o command= 2>/dev/null | sed 's/^[[:space:]]*//' || true)"
if [ -z "$cmd" ]; then
  cmd="unknown"
fi

echo "PID=${pid} CMD=${cmd}"
