# Backlog (Issue-Oriented)

This file is the live issue-style backlog for `{hatori}`.

Legend:
- `P0` critical
- `P1` high
- `P2` normal
- Status: `open`, `in_progress`, `blocked`, `done`

## Open Issues

1. `[P0][open]` Routing quality guard for writer lane
- Goal: reduce repetition and awkward style in HU planning/chat outputs.
- Acceptance:
  - golden checks for checklist quality and priority phrasing
  - no leakage-rail regressions

2. `[P0][open]` Model bootstrap reproducibility on clean host
- Goal: one-command setup installs deps, pulls required models, validates health.
- Acceptance:
  - `make bootstrap && make doctor` passes on clean machine
  - docs include exact prerequisites and expected output

3. `[P1][open]` Integrator observability pack
- Goal: improve `/v1/health` and runbook diagnostics for partner apps.
- Acceptance:
  - clear backend/routing state and breaker-like status fields
  - troubleshooting section updated for integrators

4. `[P1][open]` Bulk ingest channel expansion (email)
- Goal: operationalize reliable email ingestion flow matching iMessage loop.
- Acceptance:
  - documented payload mapping
  - idempotent replay behavior verified in integration acceptance

5. `[P1][open]` Menu bar shortcuts for core web surfaces
- Goal: quick-open links for UI pages and API health from macOS menu app.
- Acceptance:
  - links resolve to configured ports from env
  - regression check for stale hardcoded ports

## In Progress

1. `[P1][in_progress]` Task-based model routing defaults
- Current: writer/drafter/judge structure exists.
- Remaining:
  - final default model map curation
  - route-specific smoke checks in CI-safe mode

## Recently Done

1. `[P0][done]` Sent Outcome Feedback B-mode
- Delivered:
  - `/v1/agent/outcome`
  - `delivery_events` table
  - idempotency via `external_outcome_id`
  - negative learning payload stores `original_text` + `final_sent_text` + `diff`

2. `[P0][done]` Single-launch local runtime path
- Delivered:
  - `make run`
  - launcher/service scripts
  - collision-safe port behavior

3. `[P1][done]` Integrator acceptance gate
- Delivered:
  - `make integration-acceptance`
  - tests ingest/respond/outcome + idempotency + auth handling

4. `[P1][done]` Port migration to 5-digit local range
- Delivered:
  - UI `23571`
  - API `23572`
  - docs and health contract aligned
