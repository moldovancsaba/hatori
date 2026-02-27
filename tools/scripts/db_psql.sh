#!/bin/bash
set -euo pipefail
CID="${CID:-hatori-pg}"
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
export PGCLIENTENCODING="${PGCLIENTENCODING:-UTF8}"
docker exec -i "$CID" psql -U hatori -d hatori "$@"
