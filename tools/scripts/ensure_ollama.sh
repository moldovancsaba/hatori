#!/usr/bin/env bash
set -euo pipefail

if [ "${HATORI_SKIP_OLLAMA_ENSURE:-0}" = "1" ]; then
  echo "OK: ollama ensure skipped by HATORI_SKIP_OLLAMA_ENSURE=1"
  exit 0
fi

need_ollama=0
model="${HATORI_MODEL:-}"
order="${HATORI_GENERATOR_ORDER:-mlx,ollama}"

if [ "$model" = "ollama" ]; then
  need_ollama=1
fi
if printf '%s' "$order" | tr '[:upper:]' '[:lower:]' | grep -q 'ollama'; then
  need_ollama=1
fi
if [ -n "${HATORI_OLLAMA_MODEL:-}" ] || [ -n "${HATORI_OLLAMA_URL:-}" ]; then
  need_ollama=1
fi

if [ "$need_ollama" -ne 1 ]; then
  echo "OK: ollama not required by current model config"
  exit 0
fi

if curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "OK: ollama already available on 127.0.0.1:11434"
  exit 0
fi

echo "INFO: ollama not reachable; trying 'brew services start ollama'"
if ! brew services start ollama >/dev/null 2>&1; then
  echo "FAIL: unable to start ollama via brew services" >&2
  echo "Install/start ollama manually or set HATORI_GENERATOR_ORDER without ollama." >&2
  exit 1
fi

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "OK: ollama is available on 127.0.0.1:11434"
    exit 0
  fi
  sleep 1
done

echo "FAIL: ollama did not become available on 127.0.0.1:11434 within 10s" >&2
exit 1
