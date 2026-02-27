#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$HOME/.config/hatori/hatori.env"
LOG_DIR="$HOME/Library/Logs/ReplyHatori"
mkdir -p "$LOG_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

if [ ! -f "$ENV_FILE" ]; then
  log "FAIL missing env file: $ENV_FILE"
  log "Run: $ROOT/tools/scripts/hatori_env_init.sh"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

UI_PORT="${UI_PORT:-8093}"
API_PORT="${API_PORT:-8094}"
export UI_PORT API_PORT

ensure_docker_stack() {
  if ! command -v docker >/dev/null 2>&1; then
    log "FAIL docker command not found in PATH=$PATH"
    return 1
  fi
  if command -v colima >/dev/null 2>&1; then
    colima start >/dev/null 2>&1 || true
    docker context use colima >/dev/null 2>&1 || true
  fi
  (cd "$ROOT" && make up) || return 1
  return 0
}

start_one() {
  local kind="$1"
  local port="$2"
  local cmd="$3"
  local owner pid owner_cmd
  owner="$($ROOT/tools/scripts/port_owner.sh "$port")"
  if [ "$owner" = "FREE" ]; then
    log "[$kind] starting on port $port"
    bash -lc "$cmd" >>"$LOG_DIR/hatori.log" 2>&1 &
    local new_pid=$!
    log "[$kind] started pid=$new_pid"
    return 0
  fi

  pid="$(printf '%s\n' "$owner" | sed -n 's/^PID=\([0-9][0-9]*\).*/\1/p')"
  owner_cmd="$(printf '%s\n' "$owner" | sed -n 's/^PID=[0-9][0-9]* CMD=//p')"
  if "$ROOT/tools/scripts/is_hatori_pid.sh" "$pid" "$kind"; then
    log "[$kind] already running pid=$pid on port $port"
    return 0
  fi

  log "[$kind] foreign process owns port $port pid=${pid:-unknown}; will retry in 60s"
  log "[$kind] foreign cmd: ${owner_cmd:-unknown}"
  return 2
}

until ensure_docker_stack; do
  log "Retrying docker/db startup in 5s"
  sleep 5
done
if [ "${HATORI_SKIP_OLLAMA_ENSURE:-0}" != "1" ]; then
  "$ROOT/tools/scripts/ensure_ollama.sh" || true
fi

api_backoff=1
ui_backoff=1
while true; do
  if start_one api "$API_PORT" ". $ROOT/.venv/bin/activate && HATORI_API_TOKEN=\${HATORI_API_TOKEN:?set HATORI_API_TOKEN} python -m uvicorn api.app:app --host 127.0.0.1 --port $API_PORT"; then
    api_backoff=1
  else
    rc=$?
    if [ "$rc" -eq 2 ]; then
      sleep 60
    else
      sleep "$api_backoff"
      api_backoff=$(( api_backoff < 30 ? api_backoff * 2 : 30 ))
    fi
  fi

  if start_one ui "$UI_PORT" ". $ROOT/.venv/bin/activate && python -m uvicorn ui.app:app --host 127.0.0.1 --port $UI_PORT"; then
    ui_backoff=1
  else
    rc=$?
    if [ "$rc" -eq 2 ]; then
      sleep 60
    else
      sleep "$ui_backoff"
      ui_backoff=$(( ui_backoff < 30 ? ui_backoff * 2 : 30 ))
    fi
  fi

  sleep 2
done
