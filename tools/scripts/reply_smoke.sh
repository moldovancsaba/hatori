#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="$HOME/.config/hatori/hatori.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE"
  echo "Start with make run or make install-service"
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"
BASE_URL="${HATORI_BASE_URL:-http://127.0.0.1:${API_PORT:-8094}}"
TOKEN="${HATORI_API_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  echo "HATORI_API_TOKEN missing in $ENV_FILE"
  exit 1
fi

if ! curl -fsS "$BASE_URL/v1/health" >/dev/null; then
  echo "Start with make run"
  exit 2
fi

RESP=$(curl -fsS -X POST "$BASE_URL/v1/agent/respond" \
  -H "Content-Type: application/json" \
  -H "X-Hatori-Token: $TOKEN" \
  -d '{"conversation_id":"reply:smoke-thread","message_id":"reply:smoke-msg-1","sender_id":"reply:smoke-user","message":"Szia! Adj rövid választ.","metadata":{"platform":"imessage"}}')
AID=$(printf '%s' "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['assistant_interaction_id'])")
ORIG=$(printf '%s' "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['assistant_message'])")

curl -fsS -X POST "$BASE_URL/v1/agent/outcome" \
  -H "Content-Type: application/json" \
  -H "X-Hatori-Token: $TOKEN" \
  -d "{\"external_outcome_id\":\"reply:smoke-outcome-1\",\"assistant_interaction_id\":\"$AID\",\"status\":\"sent_as_is\",\"platform\":\"imessage\"}" >/dev/null

FINAL="Szia! Persze, segítek."
DIFF=$(ORIG="$ORIG" FINAL="$FINAL" python3 - <<'PY'
import difflib, os
orig = os.environ.get('ORIG','')
final = os.environ.get('FINAL','')
print(''.join(difflib.unified_diff(orig.splitlines(True), final.splitlines(True), fromfile='original', tofile='final')))
PY
)

PAYLOAD=$(AID="$AID" ORIG="$ORIG" FINAL="$FINAL" DIFF="$DIFF" python3 - <<'PY'
import json, os
print(json.dumps({
  "external_outcome_id":"reply:smoke-outcome-2",
  "assistant_interaction_id":os.environ["AID"],
  "status":"edited_then_sent",
  "platform":"imessage",
  "original_text":os.environ["ORIG"],
  "final_sent_text":os.environ["FINAL"],
  "diff":os.environ["DIFF"],
  "edit_reason":"smoke",
}, ensure_ascii=False))
PY
)

curl -fsS -X POST "$BASE_URL/v1/agent/outcome" \
  -H "Content-Type: application/json" \
  -H "X-Hatori-Token: $TOKEN" \
  -d "$PAYLOAD" >/dev/null

echo "PASS: reply-smoke"
