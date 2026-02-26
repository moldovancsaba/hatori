#!/bin/bash
set -euo pipefail
CID="${CID:-hatori-pg}"
docker exec -i "$CID" psql -U hatori -d hatori -c "DROP TABLE IF EXISTS embeddings, audit_events, learning_events, interaction_events, artefacts, pks_records CASCADE;"
docker exec -i "$CID" psql -U hatori -d hatori -c "DROP TYPE IF EXISTS pks_module, pks_status, pks_provenance, pks_confidence, pks_sensitivity, refresh_cadence CASCADE;"
docker cp pks/migrations/0001_init.sql "$CID":/0001_init.sql
docker exec -i "$CID" psql -U hatori -d hatori -f /0001_init.sql
./tools/scripts/db_seed.sh
echo "OK: reset + migrate + seed complete"
