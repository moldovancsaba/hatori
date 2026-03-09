#!/usr/bin/env bash
set -euo pipefail

NAME="${HATORI_SEARXNG_CONTAINER:-hatori-searxng}"
docker rm -f "$NAME" >/dev/null 2>&1 || true
echo "SearXNG removed: ${NAME}"
