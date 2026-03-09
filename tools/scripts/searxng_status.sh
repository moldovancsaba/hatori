#!/usr/bin/env bash
set -euo pipefail

PORT="${HATORI_SEARXNG_PORT:-8888}"
URL="${HATORI_SEARXNG_URL:-http://127.0.0.1:${PORT}}"
NAME="${HATORI_SEARXNG_CONTAINER:-hatori-searxng}"

echo "container: $NAME"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | (head -n 1; grep "$NAME" || true)
echo
echo "health probe: ${URL}/search?q=test&format=json&engines=wikipedia"
curl -fsS -m 8 -H "X-Forwarded-For: 127.0.0.1" -H "X-Real-IP: 127.0.0.1" "${URL}/search?q=test&format=json&engines=wikipedia" >/dev/null && echo "status: ok" || echo "status: unavailable"
