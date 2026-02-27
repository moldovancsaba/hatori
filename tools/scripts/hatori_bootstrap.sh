#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

./tools/scripts/hatori_env_init.sh

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r ui/requirements.txt

make up
make reset

if command -v ollama >/dev/null 2>&1; then
  ./tools/scripts/hatori_models_pull.sh
else
  echo "WARN: ollama not found; skipping model pull"
fi

make install-service
make service-status || true

echo "Bootstrap complete."
echo "UI:  http://127.0.0.1:${UI_PORT:-23571}/chat"
echo "API: http://127.0.0.1:${API_PORT:-23572}/v1/health"
