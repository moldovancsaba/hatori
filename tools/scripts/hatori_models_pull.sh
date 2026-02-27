#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="$HOME/.config/hatori/hatori.env"
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "FAIL: ollama CLI not found. Install Ollama first."
  exit 1
fi

models=()
add_model() {
  local m="${1:-}"
  if [ -n "$m" ]; then
    models+=("$m")
  fi
}

# Core/fallback models
add_model "${HATORI_OLLAMA_MODEL:-llama3.2:3b}"

# Route models
for var in \
  HATORI_ROUTE_REPLY_WRITE_MODEL \
  HATORI_ROUTE_REPLY_WRITE_FALLBACK_MODEL \
  HATORI_ROUTE_PLAN_WRITE_MODEL \
  HATORI_ROUTE_PLAN_WRITE_FALLBACK_MODEL \
  HATORI_ROUTE_REWRITE_POLISH_MODEL \
  HATORI_ROUTE_REWRITE_POLISH_FALLBACK_MODEL \
  HATORI_ROUTE_CLASSIFY_INTENT_MODEL \
  HATORI_ROUTE_CLASSIFY_INTENT_FALLBACK_MODEL \
  HATORI_ROUTE_EXTRACT_FIELDS_MODEL \
  HATORI_ROUTE_EXTRACT_FIELDS_FALLBACK_MODEL \
  HATORI_ROUTE_CONTEXT_PACK_MODEL \
  HATORI_ROUTE_CONTEXT_PACK_FALLBACK_MODEL \
  HATORI_ROUTE_RETRIEVAL_QUERY_BUILD_MODEL \
  HATORI_ROUTE_RETRIEVAL_QUERY_BUILD_FALLBACK_MODEL \
  HATORI_ROUTE_EDIT_PATTERN_CLUSTER_MODEL \
  HATORI_ROUTE_EDIT_PATTERN_CLUSTER_FALLBACK_MODEL \
  HATORI_ROUTE_ANSWER_SCORE_MODEL \
  HATORI_ROUTE_ANSWER_SCORE_FALLBACK_MODEL \
  HATORI_ROUTE_QUALITY_GATE_MODEL \
  HATORI_ROUTE_QUALITY_GATE_FALLBACK_MODEL; do
  add_model "${!var:-}"
done

# De-duplicate
unique_models=()
for m in "${models[@]}"; do
  skip=0
  for u in "${unique_models[@]:-}"; do
    if [ "$m" = "$u" ]; then
      skip=1
      break
    fi
  done
  if [ "$skip" -eq 0 ]; then
    unique_models+=("$m")
  fi
done

echo "Pulling Ollama models (${#unique_models[@]}):"
printf ' - %s\n' "${unique_models[@]}"
for m in "${unique_models[@]}"; do
  if [ -z "$m" ]; then
    continue
  fi
  echo "== ollama pull $m"
  ollama pull "$m"
done

echo "OK: model pull complete"
