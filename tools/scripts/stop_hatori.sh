#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ui_port="${PORT:-8093}"
api_port="${API_PORT:-8094}"
target="${1:-all}"

do_stop() {
  local port="$1"
  local kind="$2"
  local owner pid cmd

  owner="$(${root_dir}/tools/scripts/port_owner.sh "$port" || true)"
  if [ "$owner" = "FREE" ] || [ -z "$owner" ]; then
    echo "[${kind}] not running on ${port}"
    return 0
  fi

  pid="$(printf '%s\n' "$owner" | sed -n 's/^PID=\([0-9][0-9]*\).*/\1/p')"
  cmd="$(printf '%s\n' "$owner" | sed -n 's/^PID=[0-9][0-9]* CMD=//p')"
  if [ -z "$pid" ]; then
    echo "[${kind}] unable to parse owner for port ${port}" >&2
    return 0
  fi

  if ! "${root_dir}/tools/scripts/is_hatori_pid.sh" "$pid" "$kind"; then
    echo "SKIP: not Hatori (${kind}) PID=${pid} CMD=${cmd:-unknown}"
    return 0
  fi

  echo "[${kind}] stopping pid=${pid} on ${port}"
  kill -TERM "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "[${kind}] stopped"
      return 0
    fi
    sleep 0.2
  done

  echo "[${kind}] TERM timeout; sending KILL pid=${pid}"
  kill -KILL "$pid" 2>/dev/null || true
  return 0
}

case "$target" in
  ui)
    do_stop "$ui_port" ui
    ;;
  api)
    do_stop "$api_port" api
    ;;
  all)
    do_stop "$ui_port" ui
    do_stop "$api_port" api
    ;;
  *)
    echo "usage: $0 [ui|api|all]" >&2
    exit 2
    ;;
esac
