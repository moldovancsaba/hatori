#!/bin/bash
set -euo pipefail

cd /Users/moldovancsaba/Projects/reply-hatori
. ./tools/scripts/db_lock.sh

echo "== Hatori planning check ==" 

echo "-- Repo sanity"
pwd
ls >/dev/null

echo "-- DB status"
if docker ps >/dev/null 2>&1; then make status; else echo "WARN: docker not reachable; start Docker Desktop or colima"; fi

echo "-- Reset + tests"
if docker ps >/dev/null 2>&1; then
  db_lock_acquire
  make reset
  make test
  db_lock_release
else
  echo "SKIP: make reset (docker not reachable)"
  echo "SKIP: make test (docker not reachable)"
fi

echo "-- UI import sanity"
. .venv/bin/activate && python -c "import ui.app as m; print(\"UI app present:\", hasattr(m, \"app\"))"

echo "OK: planning check complete"
