#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$HOME/.config/hatori/hatori.env"
LOG_DIR="$HOME/Library/Logs/Hatori"
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
DOCKER_RETRY_INTERVAL="${DOCKER_RETRY_INTERVAL:-30}"
DOCKER_LAST_ATTEMPT_EPOCH=0
DOCKER_LAST_STATE=""
DOCKER_LOCK_DIR="/tmp/hatori_docker_bootstrap.lockdir"

ensure_docker_stack() {
  if ! command -v docker >/dev/null 2>&1; then
    log "FAIL docker command not found in PATH=$PATH"
    return 1
  fi
  if command -v colima >/dev/null 2>&1; then
    if ! colima status >/dev/null 2>&1; then
      if ! colima start >/dev/null 2>&1; then
        log "[docker] colima start failed"
        return 1
      fi
    fi
    docker context use colima >/dev/null 2>&1 || true
  fi
  (cd "$ROOT" && make up) || return 1
  return 0
}

try_bootstrap_docker_stack() {
  local now rc
  now="$(date +%s)"
  if [ $((now - DOCKER_LAST_ATTEMPT_EPOCH)) -lt "$DOCKER_RETRY_INTERVAL" ]; then
    return 0
  fi
  DOCKER_LAST_ATTEMPT_EPOCH="$now"

  if ! mkdir "$DOCKER_LOCK_DIR" 2>/dev/null; then
    if [ "$DOCKER_LAST_STATE" != "locked" ]; then
      log "[docker] bootstrap already in progress; skipping"
      DOCKER_LAST_STATE="locked"
    fi
    return 0
  fi

  if ensure_docker_stack; then
    if [ "$DOCKER_LAST_STATE" != "ok" ]; then
      log "[docker] stack ready"
      DOCKER_LAST_STATE="ok"
    fi
  else
    rc=$?
    if [ "$DOCKER_LAST_STATE" != "fail:$rc" ]; then
      log "[docker] stack bootstrap failed (rc=$rc); retry in ${DOCKER_RETRY_INTERVAL}s"
      DOCKER_LAST_STATE="fail:$rc"
    fi
  fi
  rmdir "$DOCKER_LOCK_DIR" >/dev/null 2>&1 || true
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
    return 0
  fi

  log "[$kind] foreign process owns port $port pid=${pid:-unknown}; cmd=${owner_cmd:-unknown}; retry in 60s"
  return 2
}

if [ "${HATORI_SKIP_OLLAMA_ENSURE:-0}" != "1" ]; then
  "$ROOT/tools/scripts/ensure_ollama.sh" || true
fi

api_backoff=1
ui_backoff=1
last_api=""
last_ui=""
while true; do
  try_bootstrap_docker_stack

  if start_one api "$API_PORT" "set -a; . \"$ENV_FILE\"; set +a; . $ROOT/.venv/bin/activate && HATORI_API_TOKEN=\${HATORI_API_TOKEN:?set HATORI_API_TOKEN} python -m uvicorn api.app:app --host 127.0.0.1 --port $API_PORT"; then
    api_owner="$($ROOT/tools/scripts/port_owner.sh "$API_PORT" 2>/dev/null || true)"
    api_state="api:${api_owner}"
    if [ "$api_state" != "$last_api" ]; then
      log "[api] state: ${api_owner:-unknown}"
      last_api="$api_state"
    fi
    api_backoff=1
  else
    rc=$?
    if [ "$rc" -eq 2 ]; then
      last_api="api:foreign"
      sleep 60
    else
      sleep "$api_backoff"
      api_backoff=$(( api_backoff < 30 ? api_backoff * 2 : 30 ))
    fi
  fi

  if start_one ui "$UI_PORT" "set -a; . \"$ENV_FILE\"; set +a; . $ROOT/.venv/bin/activate && python -m uvicorn ui.app:app --host 127.0.0.1 --port $UI_PORT"; then
    ui_owner="$($ROOT/tools/scripts/port_owner.sh "$UI_PORT" 2>/dev/null || true)"
    ui_state="ui:${ui_owner}"
    if [ "$ui_state" != "$last_ui" ]; then
      log "[ui] state: ${ui_owner:-unknown}"
      last_ui="$ui_state"
    fi
    ui_backoff=1
  else
    rc=$?
    if [ "$rc" -eq 2 ]; then
      last_ui="ui:foreign"
      sleep 60
    else
      sleep "$ui_backoff"
      ui_backoff=$(( ui_backoff < 30 ? ui_backoff * 2 : 30 ))
    fi
  fi

  sleep 2
done
