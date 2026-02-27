#!/bin/bash
set -euo pipefail

TARGET="$HOME/.config/hatori/api.env"
mkdir -p "$(dirname "$TARGET")"

if [ ! -f "$TARGET" ]; then
  python3 - <<'PY'
import secrets
from pathlib import Path
p = Path.home()/'.config'/'hatori'/'api.env'
if not p.exists():
    token = secrets.token_urlsafe(32)
    p.write_text(f'HATORI_API_TOKEN={token}\n', encoding='utf-8')
PY
  chmod 600 "$TARGET"
  echo "Created $TARGET"
else
  chmod 600 "$TARGET"
  echo "Exists $TARGET"
fi

echo "Next steps:"
echo "- Edit $TARGET if you want to rotate the token."
echo "- Start API with: source $TARGET && API_PORT=8094 make run-api"
echo "- Keep this file out of git."
