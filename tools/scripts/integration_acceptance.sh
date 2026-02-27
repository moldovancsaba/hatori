#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${HATORI_ENV_FILE:-$HOME/.config/hatori/hatori.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "FAIL: missing env file: $ENV_FILE"
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

BASE_URL="${HATORI_BASE_URL:-http://127.0.0.1:${API_PORT:-23572}}"
TOKEN="${HATORI_API_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  echo "FAIL: HATORI_API_TOKEN missing in $ENV_FILE"
  exit 1
fi

pyjson() {
  python3 -c "$1"
}

http_code() {
  curl -s -o /dev/null -w "%{http_code}" "$@"
}

echo "== integration acceptance =="
echo "base_url: $BASE_URL"

hc=$(http_code "$BASE_URL/v1/health")
if [ "$hc" != "200" ]; then
  echo "FAIL: /v1/health HTTP=$hc"
  exit 2
fi
echo "OK: health"

suffix=$(python3 - <<'PY'
import uuid
print(uuid.uuid4().hex[:10])
PY
)
thread="reply:acc-thread-$suffix"
msgid="reply:acc-msg-$suffix"

ingest_id="reply:acc-ingest-$suffix"
ingest_payload=$(python3 - <<PY
import json
print(json.dumps({
  "external_event_id": "$ingest_id",
  "kind": "imessage",
  "conversation_id": "$thread",
  "sender_id": "reply:acc-user",
  "content": "Acceptance ingest content $suffix",
  "metadata": {"platform":"imessage","channel":"sms"}
}, ensure_ascii=False))
PY
)

r1=$(curl -sS -X POST "$BASE_URL/v1/ingest/event" \
  -H "Content-Type: application/json" -H "X-Hatori-Token: $TOKEN" -d "$ingest_payload")
r2=$(curl -sS -X POST "$BASE_URL/v1/ingest/event" \
  -H "Content-Type: application/json" -H "X-Hatori-Token: $TOKEN" -d "$ingest_payload")

dup2=$(printf '%s' "$r2" | pyjson 'import sys,json; print(json.load(sys.stdin).get("duplicate"))')
if [ "$dup2" != "True" ] && [ "$dup2" != "true" ]; then
  echo "FAIL: ingest idempotency duplicate=true expected"
  echo "$r2"
  exit 3
fi
echo "OK: ingest idempotency"

respond_payload=$(python3 - <<PY
import json
print(json.dumps({
  "conversation_id": "$thread",
  "message_id": "$msgid",
  "sender_id": "reply:acc-user",
  "message": "Szia! Kérlek adj rövid választ.",
  "metadata": {"platform":"imessage"}
}, ensure_ascii=False))
PY
)

resp=$(curl -sS -X POST "$BASE_URL/v1/agent/respond" \
  -H "Content-Type: application/json" -H "X-Hatori-Token: $TOKEN" -d "$respond_payload")

aid=$(printf '%s' "$resp" | pyjson 'import sys,json; d=json.load(sys.stdin); print(d.get("assistant_interaction_id",""))')
amsg=$(printf '%s' "$resp" | pyjson 'import sys,json; d=json.load(sys.stdin); print(d.get("assistant_message",""))')
if [ -z "$aid" ] || [ -z "$amsg" ]; then
  echo "FAIL: respond missing assistant_interaction_id or assistant_message"
  echo "$resp"
  exit 4
fi
echo "OK: respond"

outcome1_id="reply:acc-outcome-sent-$suffix"
outcome1_payload=$(python3 - <<PY
import json
print(json.dumps({
  "external_outcome_id": "$outcome1_id",
  "assistant_interaction_id": "$aid",
  "conversation_id": "$thread",
  "platform": "imessage",
  "status": "sent_as_is"
}, ensure_ascii=False))
PY
)

o1=$(curl -sS -X POST "$BASE_URL/v1/agent/outcome" \
  -H "Content-Type: application/json" -H "X-Hatori-Token: $TOKEN" -d "$outcome1_payload")
o1b=$(curl -sS -X POST "$BASE_URL/v1/agent/outcome" \
  -H "Content-Type: application/json" -H "X-Hatori-Token: $TOKEN" -d "$outcome1_payload")
dup_o1b=$(printf '%s' "$o1b" | pyjson 'import sys,json; print(json.load(sys.stdin).get("duplicate"))')
if [ "$dup_o1b" != "True" ] && [ "$dup_o1b" != "true" ]; then
  echo "FAIL: outcome sent_as_is idempotency duplicate=true expected"
  echo "$o1b"
  exit 5
fi
echo "OK: outcome sent_as_is idempotency"

bad_edit_id="reply:acc-outcome-bad-$suffix"
bad_edit_payload=$(python3 - <<PY
import json
print(json.dumps({
  "external_outcome_id": "$bad_edit_id",
  "assistant_interaction_id": "$aid",
  "status": "edited_then_sent",
  "platform": "imessage"
}, ensure_ascii=False))
PY
)

bad_code=$(http_code -X POST "$BASE_URL/v1/agent/outcome" \
  -H "Content-Type: application/json" -H "X-Hatori-Token: $TOKEN" -d "$bad_edit_payload")
if [ "$bad_code" != "400" ]; then
  echo "FAIL: edited_then_sent missing fields should return 400, got $bad_code"
  exit 6
fi
echo "OK: edited_then_sent validation"

final="Szia! Persze, segítek pontosabban."
diff_text=$(ORIG="$amsg" FINAL="$final" python3 - <<'PY'
import difflib, os
orig=os.environ.get('ORIG','')
final=os.environ.get('FINAL','')
print(''.join(difflib.unified_diff(orig.splitlines(True), final.splitlines(True), fromfile='original', tofile='final')))
PY
)

outcome2_id="reply:acc-outcome-edit-$suffix"
outcome2_payload=$(AID="$aid" THREAD="$thread" OID="$outcome2_id" ORIG="$amsg" FINAL="$final" DIFF="$diff_text" python3 - <<'PY'
import json, os
print(json.dumps({
  "external_outcome_id": os.environ["OID"],
  "assistant_interaction_id": os.environ["AID"],
  "conversation_id": os.environ["THREAD"],
  "platform": "imessage",
  "status": "edited_then_sent",
  "original_text": os.environ["ORIG"],
  "final_sent_text": os.environ["FINAL"],
  "diff": os.environ["DIFF"],
  "edit_reason": "acceptance"
}, ensure_ascii=False))
PY
)

o2=$(curl -sS -X POST "$BASE_URL/v1/agent/outcome" \
  -H "Content-Type: application/json" -H "X-Hatori-Token: $TOKEN" -d "$outcome2_payload")
o2b=$(curl -sS -X POST "$BASE_URL/v1/agent/outcome" \
  -H "Content-Type: application/json" -H "X-Hatori-Token: $TOKEN" -d "$outcome2_payload")
dup_o2b=$(printf '%s' "$o2b" | pyjson 'import sys,json; print(json.load(sys.stdin).get("duplicate"))')
if [ "$dup_o2b" != "True" ] && [ "$dup_o2b" != "true" ]; then
  echo "FAIL: outcome edited_then_sent idempotency duplicate=true expected"
  echo "$o2b"
  exit 7
fi
echo "OK: outcome edited_then_sent + unified diff + idempotency"

unauth=$(http_code -X POST "$BASE_URL/v1/agent/respond" -H "Content-Type: application/json" -d "$respond_payload")
if [ "$unauth" != "401" ]; then
  echo "FAIL: unauthorized respond should be 401, got $unauth"
  exit 8
fi
echo "OK: auth enforcement"

echo "PASS: integration acceptance"
