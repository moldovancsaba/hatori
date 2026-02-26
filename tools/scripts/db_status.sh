#!/bin/bash
set -euo pipefail
CID="${1:-hatori-pg}"
docker ps --format "{{.Names}}" | grep -qx "$CID" || { echo "FAIL: container not running: $CID"; exit 1; }
docker exec -i "$CID" psql -U hatori -d hatori -c "SELECT now() as db_time;" >/dev/null
echo "OK: Postgres reachable ($CID)"
docker exec -i "$CID" psql -U hatori -d hatori -c "SELECT extname FROM pg_extension WHERE extname='vector';" | grep -q vector && echo "OK: pgvector installed" || (echo "FAIL: pgvector missing"; exit 1)
