#!/bin/bash
set -euo pipefail

. "$(dirname "$0")/db_lock.sh"
db_lock_acquire

./tools/scripts/db_status.sh >/dev/null
echo "OK: db_status"

./tools/scripts/db_psql.sh -c "\dt" | grep -q "pks_records" && echo "OK: table pks_records" || (echo "FAIL: table pks_records"; exit 1)
./tools/scripts/db_psql.sh -c "\dt" | grep -q "interaction_events" && echo "OK: table interaction_events" || (echo "FAIL: table interaction_events"; exit 1)
./tools/scripts/db_psql.sh -c "\dt" | grep -q "learning_events" && echo "OK: table learning_events" || (echo "FAIL: table learning_events"; exit 1)

RID="11111111-1111-1111-1111-111111111111"
IID="22222222-2222-2222-2222-222222222222"
LID="33333333-3333-3333-3333-333333333333"
RULE_ID="0c942328-f2cb-4293-8a7e-9c0574d51301"

./tools/scripts/db_psql.sh -t -c "SELECT 1 FROM pks_records WHERE id='$RID';" | grep -q 1 && echo "OK: seed pks_record" || (echo "FAIL: seed pks_record"; exit 1)
./tools/scripts/db_psql.sh -t -c "SELECT 1 FROM interaction_events WHERE id='$IID';" | grep -q 1 && echo "OK: seed interaction_event" || (echo "FAIL: seed interaction_event"; exit 1)
./tools/scripts/db_psql.sh -t -c "SELECT 1 FROM learning_events WHERE id='$LID';" | grep -q 1 && echo "OK: seed learning_event" || (echo "FAIL: seed learning_event"; exit 1)
./tools/scripts/db_psql.sh -t -c "SELECT 1 FROM pks_records WHERE id='$RULE_ID' AND module='H' AND status='Approved';" | grep -q 1 && echo "OK: delivery hygiene rule approved" || (echo "FAIL: delivery hygiene rule missing/not approved"; exit 1)
./tools/scripts/db_psql.sh -t -c "SELECT 1 FROM audit_events WHERE target_id='$RULE_ID' LIMIT 1;" | grep -q 1 && echo "OK: delivery hygiene rule audit trail" || (echo "FAIL: delivery hygiene rule audit missing"; exit 1)

echo "PASS: self_test"
