#!/bin/bash
set -euo pipefail

. "$(dirname "$0")/db_lock.sh"
db_lock_acquire

CID="${CID:-hatori-pg}"
docker exec -i "$CID" psql -U hatori -d hatori -c "DROP TABLE IF EXISTS embeddings, delivery_events, audit_events, learning_events, interaction_events, artefacts, pks_records CASCADE;"
docker exec -i "$CID" psql -U hatori -d hatori -c "DROP TYPE IF EXISTS pks_module, pks_status, pks_provenance, pks_confidence, pks_sensitivity, refresh_cadence CASCADE;"
for f in pks/migrations/*.sql; do
  base="$(basename "$f")"
  docker cp "$f" "$CID":"/$base"
  docker exec -i "$CID" psql -U hatori -d hatori -f "/$base"
done
./tools/scripts/db_seed.sh
echo "OK: reset + migrate + seed complete"
