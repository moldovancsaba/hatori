# Project Management (SSOT)

SSOT board:
- https://github.com/users/moldovancsaba/projects/1

Rule:
- Product repository and project repository can differ.
- For `{hatori}`, card/issue tracking lives in `moldovancsaba/mvp-factory-control`.
- Delivery work is not considered valid unless the SSOT card is updated on the board.

## Cross-Repo Board Update

Canonical issue repo (SSOT):
- `moldovancsaba/mvp-factory-control`

Example issue:
- `https://github.com/moldovancsaba/mvp-factory-control/issues/339`

Use helper script:

```bash
ISSUE_NUMBER=339 \
STATUS='In Progress (NOW)' \
PRODUCT='{hatori}' \
TYPE='Refactor' \
NOTE='Start: objective + approach + evidence plan' \
tools/scripts/ssot_board_update.sh
```

What the script does:
- Ensures the SSOT issue is attached to Project #1.
- Sets board fields:
  - `Status`
  - `Product`
  - `Type`
- Optionally posts a start/progress note to the SSOT issue.

## Manual Fallback (if script not available)

```bash
gh project item-add 1 --owner moldovancsaba --url "https://github.com/moldovancsaba/mvp-factory-control/issues/<ISSUE_NUMBER>"
gh project item-list 1 --owner moldovancsaba --limit 500 --format json
gh project item-edit --project-id PVT_kwHOACGtF84BOtVF --id <ITEM_ID> --field-id PVTSSF_lAHOACGtF84BOtVFzg9VH2o --single-select-option-id 47fc9ee4
gh issue comment <ISSUE_NUMBER> --repo moldovancsaba/mvp-factory-control --body "Progress note + evidence"
```

## Required Cadence

- Start: move card to `In Progress (NOW)` and post start note.
- Milestone: add short progress note with evidence.
- Blocker: set `Blocked` and post blocker + next attempt.
- Done: set `Done` and post acceptance + validation evidence.
