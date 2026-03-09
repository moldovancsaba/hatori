#!/usr/bin/env bash
set -euo pipefail

target="${1:-all}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${HOME}/.config/hatori/hatori.env"
if [ -f "$env_file" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$env_file"
  set +a
fi
ui_port="${UI_PORT:-${PORT:-8093}}"
api_port="${API_PORT:-8094}"

stop_one() {
  local port="$1"
  local kind="$2"
  local owner pid cmd
  owner="$(${root}/tools/scripts/port_owner.sh "$port" || true)"
  if [ "$owner" = "FREE" ] || [ -z "$owner" ]; then
    echo "[${kind}] not running on ${port}"
    return 0
  fi
  pid="$(printf '%s\n' "$owner" | sed -n 's/^PID=\([0-9][0-9]*\).*/\1/p')"
  cmd="$(printf '%s\n' "$owner" | sed -n 's/^PID=[0-9][0-9]* CMD=//p')"
  if [ -z "$pid" ] || ! "${root}/tools/scripts/is_hatori_pid.sh" "$pid" "$kind"; then
    echo "SKIP: not Hatori (${kind}) PID=${pid:-unknown} CMD=${cmd:-unknown}"
    return 0
  fi
  echo "[${kind}] stopping pid=${pid} on ${port}"
  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 15); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "[${kind}] stopped"
      return 0
    fi
    sleep 0.2
  done
  echo "[${kind}] TERM timeout; sending KILL pid=${pid}"
  kill -KILL "$pid" 2>/dev/null || true
}

case "$target" in
  ui) stop_one "$ui_port" ui ;;
  api) stop_one "$api_port" api ;;
  all) stop_one "$ui_port" ui; stop_one "$api_port" api ;;
  *) echo "usage: $0 [ui|api|all]" >&2; exit 2 ;;
esac
