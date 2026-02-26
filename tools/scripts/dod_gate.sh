#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

RULE_ID="0c942328-f2cb-4293-8a7e-9c0574d51301"

[[ -s VERSION ]] || { echo "FAIL: VERSION missing/empty"; exit 1; }
[[ -s CHANGELOG.md ]] || { echo "FAIL: CHANGELOG.md missing/empty"; exit 1; }

VERSION_VALUE="$(tr -d '[:space:]' < VERSION)"
echo "$VERSION_VALUE" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || { echo "FAIL: VERSION must be SemVer (x.y.z)"; exit 1; }
grep -q "## \[$VERSION_VALUE\]" CHANGELOG.md || { echo "FAIL: CHANGELOG.md missing heading for VERSION=$VERSION_VALUE"; exit 1; }

grep -q "Delivery hygiene (mandatory for every task)" docs/07-runbooks/runbook-dev-handoff.md || { echo "FAIL: DoD delivery hygiene clause missing in runbook-dev-handoff.md"; exit 1; }
grep -q "Engineering delivery hygiene" docs/01-charters/hatori-charter-v3.md || { echo "FAIL: charter delivery hygiene clause missing"; exit 1; }
grep -q "Before declaring done" docs/09-prompts/developer-agent-starter.md || { echo "FAIL: developer-agent-starter delivery hygiene clause missing"; exit 1; }

./tools/scripts/db_psql.sh -t -A -c "SELECT status FROM pks_records WHERE id='$RULE_ID';" | grep -qx "Approved" || {
  echo "FAIL: Delivery Hygiene Rule missing or not Approved in PKS"
  exit 1
}

./tools/scripts/db_psql.sh -t -A -c "SELECT count(*) FROM audit_events WHERE target_id='$RULE_ID';" | grep -Eq '^[1-9][0-9]*$' || {
  echo "FAIL: Delivery Hygiene Rule has no audit_events rows"
  exit 1
}

echo "PASS: dod_gate"
