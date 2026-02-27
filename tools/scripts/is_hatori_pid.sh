#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <pid> <kind>" >&2
  exit 2
fi

pid="$1"
kind="$2"

cmd="$(ps -p "$pid" -o command= 2>/dev/null | sed 's/^[[:space:]]*//' || true)"
if [ -z "$cmd" ]; then
  exit 1
fi

case "$kind" in
  ui)
    expected_port="${PORT:-8093}"
    app_pat='ui\.app:app'
    ;;
  api)
    expected_port="${API_PORT:-8094}"
    app_pat='api\.app:app'
    ;;
  *)
    echo "invalid kind: $kind" >&2
    exit 2
    ;;
esac

if ! printf '%s\n' "$cmd" | grep -E -q '(^|[[:space:]])(uvicorn|python[0-9.]*[[:space:]]+-m[[:space:]]+uvicorn)[[:space:]]'; then
  exit 1
fi
if ! printf '%s\n' "$cmd" | grep -E -q "$app_pat"; then
  exit 1
fi

listen_ports="$(lsof -nP -a -p "$pid" -iTCP -sTCP:LISTEN -Fn 2>/dev/null | sed -n 's/^n.*:\([0-9][0-9]*\)$/\1/p' || true)"
if [ -z "$listen_ports" ]; then
  exit 1
fi

if printf '%s\n' "$listen_ports" | grep -qx "$expected_port"; then
  exit 0
fi

exit 1
