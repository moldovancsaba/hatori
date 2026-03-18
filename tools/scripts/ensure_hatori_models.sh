#!/usr/bin/env bash
# Ensure required Ollama models (including Granite drafter) are present so the agent is available at launch.
# Run after ensure_ollama.sh. Idempotent: only pulls missing models.
set -euo pipefail

ENV_FILE="${HOME}/.config/hatori/hatori.env"
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

# Same defaults as hatori_models_pull.sh so required list matches
HATORI_ROUTE_CLASSIFY_INTENT_MODEL="${HATORI_ROUTE_CLASSIFY_INTENT_MODEL:-granite4:350m}"
HATORI_ROUTE_EXTRACT_FIELDS_MODEL="${HATORI_ROUTE_EXTRACT_FIELDS_MODEL:-granite4:350m}"
HATORI_ROUTE_CONTEXT_PACK_MODEL="${HATORI_ROUTE_CONTEXT_PACK_MODEL:-granite4:350m}"
HATORI_ROUTE_RETRIEVAL_QUERY_BUILD_MODEL="${HATORI_ROUTE_RETRIEVAL_QUERY_BUILD_MODEL:-granite4:350m}"
HATORI_ROUTE_EDIT_PATTERN_CLUSTER_MODEL="${HATORI_ROUTE_EDIT_PATTERN_CLUSTER_MODEL:-granite4:350m}"
HATORI_ROUTE_CONTEXT_PACK_FALLBACK_MODEL="${HATORI_ROUTE_CONTEXT_PACK_FALLBACK_MODEL:-gemma3:1b}"
HATORI_ROUTE_ANSWER_SCORE_MODEL="${HATORI_ROUTE_ANSWER_SCORE_MODEL:-llama3.2:3b}"
HATORI_ROUTE_ANSWER_SCORE_FALLBACK_MODEL="${HATORI_ROUTE_ANSWER_SCORE_FALLBACK_MODEL:-gemma2:2b}"
HATORI_OLLAMA_MODEL="${HATORI_OLLAMA_MODEL:-llama3.2:3b}"

required_models=(
  "${HATORI_ROUTE_CONTEXT_PACK_MODEL}"
  "${HATORI_ROUTE_CONTEXT_PACK_FALLBACK_MODEL}"
  "${HATORI_OLLAMA_MODEL}"
  "${HATORI_ROUTE_ANSWER_SCORE_MODEL}"
  "${HATORI_ROUTE_ANSWER_SCORE_FALLBACK_MODEL}"
)

if ! command -v ollama >/dev/null 2>&1; then
  echo "OK: ollama not installed; skip model ensure"
  exit 0
fi
if ! curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "OK: ollama not reachable; skip model ensure (run ensure_ollama.sh first)"
  exit 0
fi

# Get installed model names (Ollama returns .models[].name e.g. "granite4:350m" or "ibm/granite4:350m")
installed="$(curl -fsS --max-time 5 http://127.0.0.1:11434/api/tags 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    for m in data.get('models') or []:
        name = (m.get('name') or '').strip()
        if name:
            print(name)
except Exception:
    pass
" 2>/dev/null || true)"

missing=()
for want in "${required_models[@]}"; do
  [ -z "$want" ] && continue
  found=0
  while IFS= read -r name; do
    [ -z "$name" ] && continue
    if [ "$name" = "$want" ] || [ "$name" = "ibm/$want" ] || [ "${name##*/}" = "$want" ]; then
      found=1
      break
    fi
  done <<< "$installed"
  if [ "$found" -eq 0 ]; then
    missing+=("$want")
  fi
done

if [ ${#missing[@]} -eq 0 ]; then
  echo "OK: required Ollama models present (Granite drafter + writer/judge)"
  exit 0
fi

echo "INFO: pulling missing models so agent is available: ${missing[*]}"
for m in "${missing[@]}"; do
  [ -z "$m" ] && continue
  echo "== ollama pull $m"
  ollama pull "$m" || true
done
echo "OK: model ensure complete"
