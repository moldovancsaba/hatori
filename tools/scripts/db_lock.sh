#!/bin/bash
set -euo pipefail

LOCKDIR="${HATORI_DB_LOCKDIR:-/tmp/hatori_db.lockdir}"

db_lock_acquire() {
  if [ "${HATORI_DB_LOCK_HELD:-0}" = "1" ]; then
    return 0
  fi

  if mkdir "$LOCKDIR" 2>/dev/null; then
    printf "%s\n" "$$" > "$LOCKDIR/pid" || true
    export HATORI_DB_LOCK_HELD=1
    trap 'db_lock_release' EXIT INT TERM HUP
    return 0
  fi

  echo "DB busy; retry"
  return 1
}

db_lock_release() {
  if [ "${HATORI_DB_LOCK_HELD:-0}" != "1" ]; then
    return 0
  fi

  rm -f "$LOCKDIR/pid" 2>/dev/null || true
  rmdir "$LOCKDIR" 2>/dev/null || true
  unset HATORI_DB_LOCK_HELD
  return 0
}
