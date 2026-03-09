#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <pid> <kind>" >&2
  exit 2
fi

pid="$1"
kind="$2"
env_file="${HOME}/.config/hatori/hatori.env"
if [ -f "$env_file" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$env_file"
  set +a
fi
cmd="$(ps -p "$pid" -o command= 2>/dev/null | sed 's/^[[:space:]]*//' || true)"
[ -n "$cmd" ] || exit 1

case "$kind" in
  ui)
    app_re='ui\.app:app'
    expected_port="${UI_PORT:-${PORT:-8093}}"
    ;;
  api)
    app_re='api\.app:app'
    expected_port="${API_PORT:-8094}"
    ;;
  *)
    echo "invalid kind: $kind" >&2
    exit 2
    ;;
esac

if ! printf '%s\n' "$cmd" | grep -Eq '(uvicorn|python[0-9.]*[[:space:]]+-m[[:space:]]+uvicorn)'; then
  exit 1
fi
if ! printf '%s\n' "$cmd" | grep -Eq "$app_re"; then
  exit 1
fi

listen_ports="$(lsof -nP -a -p "$pid" -iTCP -sTCP:LISTEN -Fn 2>/dev/null | sed -n 's/^n.*:\([0-9][0-9]*\)$/\1/p' || true)"
[ -n "$listen_ports" ] || exit 1
printf '%s\n' "$listen_ports" | grep -qx "$expected_port"
