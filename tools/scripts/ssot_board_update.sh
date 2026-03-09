#!/usr/bin/env bash
set -euo pipefail

# Update SSOT card fields on GitHub Project v2 when product repo differs from project repo.

OWNER="${OWNER:-moldovancsaba}"
PROJECT_NUMBER="${PROJECT_NUMBER:-1}"
SSOT_REPO="${SSOT_REPO:-moldovancsaba/mvp-factory-control}"
ISSUE_NUMBER="${ISSUE_NUMBER:-}"
STATUS="${STATUS:-In Progress (NOW)}"
PRODUCT_DEFAULT="{hatori}"
PRODUCT="${PRODUCT:-$PRODUCT_DEFAULT}"
TYPE="${TYPE:-Refactor}"
NOTE="${NOTE:-}"

PROJECT_ID="PVT_kwHOACGtF84BOtVF"
STATUS_FIELD_ID="PVTSSF_lAHOACGtF84BOtVFzg9VH2o"
PRODUCT_FIELD_ID="PVTSSF_lAHOACGtF84BOtVFzg9VLj8"
TYPE_FIELD_ID="PVTSSF_lAHOACGtF84BOtVFzg9VL78"

status_option_id() {
  case "$1" in
    "IDEA BANK") echo "0430151a" ;;
    "Roadmap (LATER)") echo "3c99057e" ;;
    "Backlog (SOONER)") echo "d047475e" ;;
    "Ready (NEXT)") echo "f75ad846" ;;
    "In Progress (NOW)") echo "47fc9ee4" ;;
    "Review") echo "bd42afa7" ;;
    "Blocked") echo "942156eb" ;;
    "Done") echo "98236657" ;;
    *) return 1 ;;
  esac
}

product_option_id() {
  case "$1" in
    "doneisbetter") echo "5a2478f0" ;;
    "WarRoom") echo "61cb32b6" ;;
    "{reply}") echo "d27ce93f" ;;
    "{hatori}") echo "e5751b8f" ;;
    "amanoba") echo "35d11f70" ;;
    "messmass") echo "23589fb5" ;;
    "launchmass") echo "0fbbb13f" ;;
    "narimato") echo "83b3eb43" ;;
    *) return 1 ;;
  esac
}

type_option_id() {
  case "$1" in
    "Feature") echo "aa33bdd1" ;;
    "Bug") echo "c6038a0b" ;;
    "Refactor") echo "cb76b8d8" ;;
    "Docs") echo "2ac73f16" ;;
    "Audit") echo "9119b20d" ;;
    "Release") echo "3440778b" ;;
    "Plan") echo "bfeb5246" ;;
    *) return 1 ;;
  esac
}

usage() {
  cat <<USAGE
Usage:
  ISSUE_NUMBER=<num> [STATUS='In Progress (NOW)'] [PRODUCT='{hatori}'] [TYPE='Refactor'] [NOTE='text'] tools/scripts/ssot_board_update.sh
USAGE
}

if [ -z "$ISSUE_NUMBER" ]; then
  usage
  exit 2
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "FAIL: gh CLI is required" >&2
  exit 1
fi

status_opt="$(status_option_id "$STATUS" || true)"
product_opt="$(product_option_id "$PRODUCT" || true)"
type_opt="$(type_option_id "$TYPE" || true)"

[ -n "$status_opt" ] || { echo "FAIL: unknown STATUS '$STATUS'" >&2; exit 2; }
[ -n "$product_opt" ] || { echo "FAIL: unknown PRODUCT '$PRODUCT'" >&2; exit 2; }
[ -n "$type_opt" ] || { echo "FAIL: unknown TYPE '$TYPE'" >&2; exit 2; }

issue_url="https://github.com/${SSOT_REPO}/issues/${ISSUE_NUMBER}"

# Ensure issue is on project; no-op if already present.
gh project item-add "$PROJECT_NUMBER" --owner "$OWNER" --url "$issue_url" >/dev/null 2>&1 || true

item_id="$({ gh project item-list "$PROJECT_NUMBER" --owner "$OWNER" --limit 500 --format json || true; } | tr '{' '\n' | grep -F "\"url\":\"${issue_url}\"" -B 2 | sed -n 's/.*"id":"\([^"]*\)".*/\1/p' | tail -n1)"

if [ -z "$item_id" ]; then
  echo "FAIL: cannot resolve project item id for ${issue_url}" >&2
  exit 1
fi

gh project item-edit --project-id "$PROJECT_ID" --id "$item_id" --field-id "$STATUS_FIELD_ID" --single-select-option-id "$status_opt"
gh project item-edit --project-id "$PROJECT_ID" --id "$item_id" --field-id "$PRODUCT_FIELD_ID" --single-select-option-id "$product_opt"
gh project item-edit --project-id "$PROJECT_ID" --id "$item_id" --field-id "$TYPE_FIELD_ID" --single-select-option-id "$type_opt"

if [ -n "$NOTE" ]; then
  gh issue comment "$ISSUE_NUMBER" --repo "$SSOT_REPO" --body "$NOTE" >/dev/null
fi

echo "OK: updated ${issue_url} on project #${PROJECT_NUMBER}" 
echo "- Item: ${item_id}" 
echo "- Status: ${STATUS}" 
echo "- Product: ${PRODUCT}" 
echo "- Type: ${TYPE}"
