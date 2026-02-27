#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$HOME/.config/hatori/hatori.env"

echo "== hatori doctor =="
echo "repo: $ROOT"

if [ -f "$ENV_FILE" ]; then
  echo "env: OK $ENV_FILE"
  # shellcheck disable=SC1090
  source "$ENV_FILE"
else
  echo "env: MISSING ($ENV_FILE)"
fi

if [ -x "$ROOT/.venv/bin/python" ]; then
  echo "venv: OK"
else
  echo "venv: MISSING (.venv)"
fi

if command -v docker >/dev/null 2>&1; then
  echo "docker: OK"
else
  echo "docker: MISSING"
fi

if command -v ollama >/dev/null 2>&1; then
  echo "ollama: OK"
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "ollama api: OK"
  else
    echo "ollama api: DOWN"
  fi
else
  echo "ollama: MISSING"
fi

API_PORT_VAL="${API_PORT:-23572}"
UI_PORT_VAL="${UI_PORT:-23571}"
printf 'api_health(%s): ' "$API_PORT_VAL"
if curl -fsS "http://127.0.0.1:${API_PORT_VAL}/v1/health" >/dev/null 2>&1; then
  echo OK
else
  echo DOWN
fi
printf 'ui_health(%s): ' "$UI_PORT_VAL"
if curl -fsS "http://127.0.0.1:${UI_PORT_VAL}/chat" >/dev/null 2>&1; then
  echo OK
else
  echo DOWN
fi

echo "== done =="
