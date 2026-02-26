#!/bin/bash
set -euo pipefail

. "$(dirname "$0")/db_lock.sh"
db_lock_acquire

CID="${CID:-hatori-pg}"
RID="11111111-1111-1111-1111-111111111111"
IID="22222222-2222-2222-2222-222222222222"
LID="33333333-3333-3333-3333-333333333333"
RULE_ID="0c942328-f2cb-4293-8a7e-9c0574d51301"
RULE_AUDIT_ID="44444444-4444-4444-4444-444444444444"
docker exec -i "$CID" psql -U hatori -d hatori -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null
docker exec -i "$CID" psql -U hatori -d hatori -c "INSERT INTO pks_records (id,module,title,body,provenance,confidence,scope) VALUES ('$RID','H','Charter source of truth','See docs/01-charters/hatori-charter-v3.md','User','High','Personal') ON CONFLICT (id) DO NOTHING;"
docker exec -i "$CID" psql -U hatori -d hatori -c "INSERT INTO pks_records (id,module,title,body,status,provenance,confidence,scope) VALUES ('$RULE_ID','H','Delivery Hygiene Rule','Always update documentation, update versioning artefacts (VERSION and CHANGELOG.md), commit all related changes, and push to origin/main before declaring a task done.','Approved','User','High','Personal') ON CONFLICT (id) DO NOTHING;"
docker exec -i "$CID" psql -U hatori -d hatori -c "INSERT INTO interaction_events (id,role,content,metadata) VALUES ('$IID','system','Seed: DB initialised','{}'::jsonb) ON CONFLICT (id) DO NOTHING;"
docker exec -i "$CID" psql -U hatori -d hatori -c "INSERT INTO learning_events (id,kind,confidence,details) VALUES ('$LID','ImplicitPositive','Low','{\"note\":\"Seed event\"}'::jsonb) ON CONFLICT (id) DO NOTHING;"
docker exec -i "$CID" psql -U hatori -d hatori -c "INSERT INTO audit_events (id,actor,action,target_type,target_id,details) VALUES ('$RULE_AUDIT_ID','system','create','pks_record','$RULE_ID','{\"source\":\"seed\",\"status\":\"Approved\"}'::jsonb) ON CONFLICT (id) DO NOTHING;"
echo "OK: seed complete"
