#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${HOME}/Library/Logs/Hatori"
LOG_FILE="${LOG_DIR}/hatori.log"
ENV_FILE="${HOME}/.config/hatori/hatori.env"
API_ENV_FILE="${HOME}/.config/hatori/api.env"
PORT_OWNER="${ROOT_DIR}/tools/scripts/port_owner.sh"
IS_HATORI_PID="${ROOT_DIR}/tools/scripts/is_hatori_pid.sh"

mkdir -p "${LOG_DIR}"
touch "${LOG_FILE}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck source=/dev/null
  set -a && source "${ENV_FILE}" && set +a
fi
if [[ -z "${HATORI_API_TOKEN:-}" && -f "${API_ENV_FILE}" ]]; then
  # shellcheck source=/dev/null
  set -a && source "${API_ENV_FILE}" && set +a
fi

UI_PORT="${UI_PORT:-23571}"
API_PORT="${API_PORT:-23572}"
API_HOST="${HATORI_API_BIND:-127.0.0.1}"
VENV_ACTIVATE="${ROOT_DIR}/.venv/bin/activate"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"${LOG_FILE}"
}

start_ui() {
  if [[ ! -f "${VENV_ACTIVATE}" ]]; then
    log "[ui] missing venv activate script at ${VENV_ACTIVATE}"
    return 1
  fi
  nohup bash -lc "cd '${ROOT_DIR}' && . '${VENV_ACTIVATE}' && python -m uvicorn ui.app:app --host 127.0.0.1 --port '${UI_PORT}'" >>"${LOG_FILE}" 2>&1 &
  log "[ui] started on :${UI_PORT} pid=$!"
}

start_api() {
  if [[ -z "${HATORI_API_TOKEN:-}" ]]; then
    log "[api] HATORI_API_TOKEN is not set; cannot start API"
    return 1
  fi
  if [[ ! -f "${VENV_ACTIVATE}" ]]; then
    log "[api] missing venv activate script at ${VENV_ACTIVATE}"
    return 1
  fi
  nohup bash -lc "cd '${ROOT_DIR}' && . '${VENV_ACTIVATE}' && HATORI_API_TOKEN='${HATORI_API_TOKEN}' HATORI_API_BIND='${API_HOST}' python -m uvicorn api.app:app --host '${API_HOST}' --port '${API_PORT}'" >>"${LOG_FILE}" 2>&1 &
  log "[api] started on :${API_PORT} pid=$!"
}

ensure_service() {
  local name="$1"
  local port="$2"

  local owner pid cmd
  owner="$("${PORT_OWNER}" "${port}" || true)"
  if [[ -n "${owner}" ]]; then
    pid="${owner%%|*}"
    cmd="${owner#*|}"
    if "${IS_HATORI_PID}" "${pid}" "${ROOT_DIR}"; then
      return 0
    fi
    log "[${name}] foreign process owns port ${port} pid=${pid}; cmd=${cmd}; retry in 60s"
    sleep 60
    return 0
  fi

  if [[ "${name}" == "ui" ]]; then
    start_ui || true
  else
    start_api || true
  fi
}

log "[service] boot: root=${ROOT_DIR} ui_port=${UI_PORT} api_port=${API_PORT}"

while true; do
  ensure_service "ui" "${UI_PORT}"
  ensure_service "api" "${API_PORT}"
  sleep 5
done
