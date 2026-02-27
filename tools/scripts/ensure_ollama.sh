#!/usr/bin/env bash
set -euo pipefail

if [ "${HATORI_SKIP_OLLAMA_ENSURE:-0}" = "1" ]; then
  echo "OK: ollama ensure skipped by HATORI_SKIP_OLLAMA_ENSURE=1"
  exit 0
fi

need=0
order="${HATORI_GENERATOR_ORDER:-mlx,ollama}"
if printf '%s' "$order" | tr '[:upper:]' '[:lower:]' | grep -q 'ollama'; then need=1; fi
if [ "${HATORI_MODEL:-}" = "ollama" ] || [ -n "${HATORI_OLLAMA_MODEL:-}" ] || [ -n "${HATORI_OLLAMA_URL:-}" ]; then need=1; fi

if [ "$need" -ne 1 ]; then
  echo "OK: ollama not required by current model config"
  exit 0
fi

if curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "OK: ollama already available on 127.0.0.1:11434"
  exit 0
fi

echo "INFO: ollama not reachable; trying brew services start ollama"
if ! command -v brew >/dev/null 2>&1; then
  echo "FAIL: brew not found; cannot auto-start ollama" >&2
  exit 1
fi
brew services start ollama >/dev/null 2>&1 || {
  echo "FAIL: unable to start ollama via brew services" >&2
  exit 1
}

for _ in $(seq 1 10); do
  if curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "OK: ollama is available on 127.0.0.1:11434"
    exit 0
  fi
  sleep 1
done

echo "FAIL: ollama did not become available on 127.0.0.1:11434 within 10s" >&2
exit 1
