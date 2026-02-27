#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NEW="$HOME/.config/hatori/hatori.env"
LEGACY="$HOME/.config/hatori/api.env"

"$ROOT/tools/scripts/hatori_env_init.sh"

if [ ! -f "$LEGACY" ]; then
  cat > "$LEGACY" <<EOF
# Deprecated: use ~/.config/hatori/hatori.env
# Kept for backward compatibility.
source "$NEW"
EOF
  chmod 600 "$LEGACY"
  echo "Created compatibility shim: $LEGACY"
else
  echo "Legacy file exists: $LEGACY"
fi

echo "Use this canonical file going forward: $NEW"
