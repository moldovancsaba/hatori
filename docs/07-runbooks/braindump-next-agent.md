> Planning SSOT: active tasks are tracked only on https://github.com/users/moldovancsaba/projects/1 (Product `{hatori}`).

# Braindump: Next Agent Continuation

Last updated: 2026-02-27

## Current state
- Repo: `/Users/moldovancsaba/Projects/hatori`
- Branch: `sprint-05-daily-planning-golden`
- HEAD: `c86928b`
- Open PR: `#4` https://github.com/moldovancsaba/hatori/pull/4
- CI (latest push): green https://github.com/moldovancsaba/hatori/actions/runs/22484817404

## What is already done
- Chat quality rails:
  - leakage blocking for UUID/`emb:`/`artefact_id`/`User request:`/internal scaffolding
  - server-side human-readable evidence rendering
  - structured planning path (`generation_path=planning_structured`) with server-rendered template
- UTF-8 hardening:
  - `tools/scripts/db_psql.sh` exports UTF-8 client encoding and locale defaults
- Local {hatori} API (localhost-only):
  - new service: `api/app.py`
  - endpoints: `/v1/health`, `/v1/agent/respond`, `/v1/agent/feedback`, `/v1/ingest/event`, `/v1/search`
  - token auth for POST via `X-Hatori-Token` and `HATORI_API_TOKEN`
  - API port reserved: `23572` and recorded in `/Users/moldovancsaba/Projects/_GENERAL_/ports.md`
- Make target:
  - `make run-api` (binds `127.0.0.1`, default `API_PORT=23572`)
- Golden tests:
  - total now `89` cases
  - includes API tests `test_92`..`test_97`

## Verified commands and outcomes
- `make test` => `PASS: golden tests (89 cases)`
- `./tools/scripts/planning_check.sh` => `OK: planning check complete`
- API proofs collected:
  - `GET /v1/health` 200
  - `POST /v1/agent/respond` without token => 401
  - `POST /v1/agent/respond` with token => 200 + linked interaction rows
  - `POST /v1/agent/feedback` => 200 + linked learning event row

## Known caveats to improve next
- API `respond` content quality can still be generic/awkward in some Hungarian responses when running with `HATORI_MODEL=none`.
- API and UI share logic through `ui.app` helpers. This is intentional for speed, but historical note: UI and API currently share helpers via `ui.app`.

## Next-agent prompt (copy/paste)
You are a developer agent working on repo:
  /Users/moldovancsaba/Projects/hatori
Remote:
  https://github.com/moldovancsaba/hatori.git
Branch to continue:
  sprint-05-daily-planning-golden
Baseline commit:
  c86928b

Mission: stabilize API response quality for `{reply}` integration while preserving governance and leakage protections.

Hard requirements:
1) Keep API contract and auth unchanged (`/v1/*`, `X-Hatori-Token`, `HATORI_API_TOKEN`).
2) Keep localhost-only binding and port separation (`UI 23571`, `API 23572`).
3) Do not regress leakage rails (no UUID, emb:, artefact_id, User request echo, internal scaffolding).
4) Keep `make test` and `planning_check.sh` green with no skipped tests.

Implementation focus:
- Improve `/v1/agent/respond` quality for Hungarian planning/chat:
  - tighten structured generation for planning and generic chat outputs
  - ensure next actions are naturally phrased Hungarian checklist items with clear priority
  - avoid awkward repetitions while keeping offline-safe constraints
- Add/adjust golden API quality tests as needed.

Verification to run:
- make test
- ./tools/scripts/planning_check.sh
- curl health/respond/feedback/search proofs on :23572

Deliverables:
- PR URL + green CI URL
- sample API respond output from DB (clean + useful Hungarian)
- summary of files changed
