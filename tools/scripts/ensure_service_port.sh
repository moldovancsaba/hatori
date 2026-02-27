#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "usage: $0 <port> <kind> <start_cmd>" >&2
  exit 2
fi

port="$1"
kind="$2"
start_cmd="$3"
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

owner="$(${root_dir}/tools/scripts/port_owner.sh "$port")"
if [ "$owner" = "FREE" ]; then
  echo "[${kind}] port ${port} is free, starting"
  exec bash -lc "$start_cmd"
fi

pid="$(printf '%s\n' "$owner" | sed -n 's/^PID=\([0-9][0-9]*\).*/\1/p')"
cmd="$(printf '%s\n' "$owner" | sed -n 's/^PID=[0-9][0-9]* CMD=//p')"

if [ -n "$pid" ] && "${root_dir}/tools/scripts/is_hatori_pid.sh" "$pid" "$kind"; then
  echo "OK: already running (${kind}) on ${port} pid=${pid}"
  if [ "$kind" = "ui" ]; then
    echo "URL: http://127.0.0.1:${port}/chat"
  else
    echo "URL: http://127.0.0.1:${port}/v1/health"
  fi
  exit 0
fi

echo "FAIL: port ${port} busy by PID=${pid:-unknown} CMD=${cmd:-unknown}" >&2
exit 1
