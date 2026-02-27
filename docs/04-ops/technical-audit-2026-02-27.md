# Technical Audit Report (2026-02-27)

Scope:
- Recent service/orchestration/menu/API integration work on branch `feat/single-launch-reply-integration`
- Hard-coded values, obsolete/deprecated paths, and optimization opportunities

## Findings and Actions

## 1) Legacy env file drift (`api.env` vs `hatori.env`)
- Finding: two env conventions existed (`~/.config/hatori/api.env` and `~/.config/hatori/hatori.env`).
- Risk: user/operator confusion and inconsistent startup behavior.
- Action taken:
  - canonicalized to `~/.config/hatori/hatori.env`
  - updated `tools/scripts/hatori_api_env.sh` to call `hatori_env_init.sh`
  - added compatibility shim behavior for legacy `api.env`

## 2) Service log spam (performance/noise)
- Finding: `hatori_service.sh` emitted repetitive "already running" lines every loop iteration.
- Risk: noisy logs and wasted I/O.
- Action taken:
  - state-change logging in supervisor loop
  - reduced repetitive logging; now logs only when state changes or on actionable errors

## 3) Hard-coded port references in menu bar app
- Finding: menu bar app used fixed `23571/23572` URLs.
- Risk: incorrect behavior if ports are overridden in env.
- Action taken:
  - menu app now reads `UI_PORT` and `API_PORT` from `~/.config/hatori/hatori.env`
  - retains defaults if values are not present

## 4) Documentation hard-coded absolute links
- Finding: some docs used absolute local filesystem links.
- Risk: non-portable references for collaborators/other machines.
- Action taken:
  - changed contract links to repo-relative paths in docs

## 5) Feedback 500 caused by JSON SQL escaping
- Finding: quote/backslash-heavy feedback text could break JSON SQL inserts.
- Risk: runtime 500 on `/chat/feedback` and missing learning rows.
- Action taken:
  - switched UI JSON writes to robust JSONB SQL literal handling
  - verified with quote/backslash-heavy feedback payload

## Remaining Recommendations

1. Add DB unique indexes for idempotency keys where not already enforced by schema, then keep app-level duplicate handling.
2. Add structured JSON logging option for service/menu actions to improve machine observability.
3. Move menu app to a signed Xcode project if distribution outside local machine is required.
4. Add optional request tracing ID in API responses for easier support/debugging.

## Verification commands

```bash
make test
./tools/scripts/planning_check.sh
make service-status
make reply-smoke
```
