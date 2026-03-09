#!/usr/bin/env bash
set -euo pipefail

# Toggle MLX usage mode in ~/.config/hatori/hatori.env.
# Modes:
# - on:     MLX enabled (default routing can use MLX)
# - off:    MLX disabled, routing falls back to configured fallback backends
# - status: print effective setting

mode="${1:-status}"
env_file="$HOME/.config/hatori/hatori.env"

if [ ! -f "$env_file" ]; then
  echo "FAIL: missing env file $env_file"
  echo "Run: tools/scripts/hatori_env_init.sh"
  exit 1
fi

print_status() {
  local value
  value="$(grep -E '^HATORI_DISABLE_MLX=' "$env_file" | tail -n1 | cut -d= -f2- || true)"
  if [ -z "$value" ] || [ "$value" = "0" ]; then
    echo "MLX mode: ON (HATORI_DISABLE_MLX=0)"
  elif [ "$value" = "1" ]; then
    echo "MLX mode: OFF (HATORI_DISABLE_MLX=1)"
  else
    echo "MLX mode: UNKNOWN (HATORI_DISABLE_MLX=${value})"
  fi
}

backup_and_force_apertus_fallback() {
  local lane backend_key model_key fb_backend_key fb_model_key backup_key
  for lane in REPLY_WRITE PLAN_WRITE REWRITE_POLISH; do
    backend_key="HATORI_ROUTE_${lane}_BACKEND"
    model_key="HATORI_ROUTE_${lane}_MODEL"
    fb_backend_key="HATORI_ROUTE_${lane}_FALLBACK_BACKEND"
    fb_model_key="HATORI_ROUTE_${lane}_FALLBACK_MODEL"
    backup_key="HATORI_ROUTE_${lane}_FALLBACK_MODEL_BACKUP"

    local backend model current_fb_model
    backend="$(grep -E "^${backend_key}=" "$env_file" | tail -n1 | cut -d= -f2- || true)"
    model="$(grep -E "^${model_key}=" "$env_file" | tail -n1 | cut -d= -f2- || true)"
    current_fb_model="$(grep -E "^${fb_model_key}=" "$env_file" | tail -n1 | cut -d= -f2- || true)"

    if [ "$(printf '%s' "$backend" | tr '[:upper:]' '[:lower:]')" = "mlx" ] && [ -n "$model" ]; then
      if ! grep -qE "^${backup_key}=" "$env_file"; then
        printf '%s=%s\n' "$backup_key" "$current_fb_model" >> "$env_file"
      fi
      if grep -qE "^${fb_backend_key}=" "$env_file"; then
        sed -i '' "s|^${fb_backend_key}=.*|${fb_backend_key}=ollama|" "$env_file"
      else
        printf '%s=%s\n' "$fb_backend_key" "ollama" >> "$env_file"
      fi
      if grep -qE "^${fb_model_key}=" "$env_file"; then
        sed -i '' "s|^${fb_model_key}=.*|${fb_model_key}=${model}|" "$env_file"
      else
        printf '%s=%s\n' "$fb_model_key" "$model" >> "$env_file"
      fi
    fi
  done
}

restore_fallback_backups() {
  local lane fb_model_key backup_key backup_val
  for lane in REPLY_WRITE PLAN_WRITE REWRITE_POLISH; do
    fb_model_key="HATORI_ROUTE_${lane}_FALLBACK_MODEL"
    backup_key="HATORI_ROUTE_${lane}_FALLBACK_MODEL_BACKUP"
    backup_val="$(grep -E "^${backup_key}=" "$env_file" | tail -n1 | cut -d= -f2- || true)"
    if grep -qE "^${backup_key}=" "$env_file"; then
      if [ -n "$backup_val" ]; then
        if grep -qE "^${fb_model_key}=" "$env_file"; then
          sed -i '' "s|^${fb_model_key}=.*|${fb_model_key}=${backup_val}|" "$env_file"
        else
          printf '%s=%s\n' "$fb_model_key" "$backup_val" >> "$env_file"
        fi
      fi
      sed -i '' "/^${backup_key}=/d" "$env_file"
    fi
  done
}

set_value() {
  local target="$1"
  if grep -qE '^HATORI_DISABLE_MLX=' "$env_file"; then
    sed -i '' "s/^HATORI_DISABLE_MLX=.*/HATORI_DISABLE_MLX=${target}/" "$env_file"
  else
    printf '\nHATORI_DISABLE_MLX=%s\n' "$target" >> "$env_file"
  fi
}

case "$mode" in
  on)
    set_value "0"
    restore_fallback_backups
    print_status
    echo "Apertus fallback backups restored for MLX lanes (if present)."
    echo "Next: restart service -> make install-service"
    ;;
  off)
    set_value "1"
    backup_and_force_apertus_fallback
    print_status
    echo "MLX lanes now use Apertus as fallback model via fallback backend."
    echo "Next: restart service -> make install-service"
    ;;
  status)
    print_status
    ;;
  *)
    echo "usage: $0 [on|off|status]"
    exit 2
    ;;
esac
