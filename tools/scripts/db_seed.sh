#!/bin/bash
set -euo pipefail
CID="${CID:-hatori-pg}"
RID="11111111-1111-1111-1111-111111111111"
IID="22222222-2222-2222-2222-222222222222"
LID="33333333-3333-3333-3333-333333333333"
docker exec -i "$CID" psql -U hatori -d hatori -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null
docker exec -i "$CID" psql -U hatori -d hatori -c "INSERT INTO pks_records (id,module,title,body,provenance,confidence,scope) VALUES ('$RID','H','Charter source of truth','See docs/01-charters/hatori-charter-v3.md','User','High','Personal') ON CONFLICT (id) DO NOTHING;"
docker exec -i "$CID" psql -U hatori -d hatori -c "INSERT INTO interaction_events (id,role,content,metadata) VALUES ('$IID','system','Seed: DB initialised','{}'::jsonb) ON CONFLICT (id) DO NOTHING;"
docker exec -i "$CID" psql -U hatori -d hatori -c "INSERT INTO learning_events (id,kind,confidence,details) VALUES ('$LID','ImplicitPositive','Low','{\"note\":\"Seed event\"}'::jsonb) ON CONFLICT (id) DO NOTHING;"
echo "OK: seed complete"
