#!/usr/bin/env bash
set -euo pipefail

NAME="${HATORI_SEARXNG_CONTAINER:-hatori-searxng}"
PORT="${HATORI_SEARXNG_PORT:-8888}"

if docker ps -a --format "{{.Names}}" | grep -qx "$NAME"; then
  docker start "$NAME" >/dev/null
else
  docker run -d \
    --name "$NAME" \
    -p "${PORT}:8080" \
    -e SEARXNG_BASE_URL="http://127.0.0.1:${PORT}/" \
    -e UWSGI_WORKERS=2 \
    searxng/searxng:latest >/dev/null
fi

# Enable JSON output for API clients and GET method for simple local integration.
docker exec -i "$NAME" python3 - <<'PY'
from pathlib import Path
p = Path("/etc/searxng/settings.yml")
s = p.read_text(encoding="utf-8")
s = s.replace('method: "POST"', 'method: "GET"')
s = s.replace("  formats:\n    - html\n", "  formats:\n    - html\n    - json\n")
p.write_text(s, encoding="utf-8")
PY
docker restart "$NAME" >/dev/null

echo "SearXNG up: http://127.0.0.1:${PORT}"
