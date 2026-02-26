#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

if [ "${HATORI_DB_LOCK_HELD:-0}" = "1" ]; then
  echo "SKIP: db_lock_contention_test (lock already held)"
  exit 0
fi

OUT_FILE="$(mktemp)"
LOCKDIR="${HATORI_DB_LOCKDIR:-/tmp/hatori_db.lockdir}"
HOLDER_PID=""

cleanup() {
  rm -f "$OUT_FILE"
  if [ -n "$HOLDER_PID" ]; then
    wait "$HOLDER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

bash -lc "cd '$ROOT_DIR'; . ./tools/scripts/db_lock.sh; db_lock_acquire; sleep 2" &
HOLDER_PID="$!"

for _ in $(seq 1 20); do
  if [ -d "$LOCKDIR" ]; then
    break
  fi
  sleep 0.1
done

if [ ! -d "$LOCKDIR" ]; then
  echo "FAIL: could not observe DB lock acquisition"
  exit 1
fi

set +e
./tools/scripts/self_test.sh >"$OUT_FILE" 2>&1
RC=$?
set -e

if [ "$RC" -eq 0 ]; then
  echo "FAIL: self_test should fail while DB lock is held"
  cat "$OUT_FILE"
  exit 1
fi

grep -q "DB busy; retry" "$OUT_FILE" || {
  echo "FAIL: expected contention message not found"
  cat "$OUT_FILE"
  exit 1
}

wait "$HOLDER_PID"
HOLDER_PID=""

./tools/scripts/self_test.sh >/dev/null
echo "PASS: db_lock_contention_test"
