#!/usr/bin/env bash
set -euo pipefail

target="$HOME/.config/hatori/hatori.env"
mkdir -p "$(dirname "$target")"
if [ ! -f "$target" ]; then
  token="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
  cat > "$target" <<ENV
HATORI_API_TOKEN=${token}
UI_PORT=8093
API_PORT=8094
HATORI_GENERATOR_ORDER=mlx,ollama
HATORI_OLLAMA_MODEL=llama3.2:3b
HATORI_MLX_MODEL=
HATORI_SKIP_OLLAMA_ENSURE=0
ENV
  chmod 600 "$target"
  echo "Created $target"
else
  chmod 600 "$target"
  echo "Exists $target"
fi

echo "Next steps:"
echo "- Edit $target if you want custom model config."
echo "- Install service: make install-service"
echo "- Token value is stored in $target (not printed)."
