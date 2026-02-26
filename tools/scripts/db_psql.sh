#!/bin/bash
set -euo pipefail
CID="${CID:-hatori-pg}"
docker exec -i "$CID" psql -U hatori -d hatori "$@"
