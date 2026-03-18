> Planning SSOT: active tasks are tracked only on https://github.com/users/moldovancsaba/projects/1 (Product `{hatori}`).

# Braindump: Next Agent Continuation

Last updated: 2026-03-16

**Refer to and use:** [docs/BRAIN_DUMP.md](../BRAIN_DUMP.md) for standing **rules** (referenceable by slug and anchor) and **gotchas**. This file is the continuation log and 70-protocol handover; BRAIN_DUMP is the single place to cite from runbooks, prompts, and code.

## 70 Protocol Handover Entry (2026-03-02 22:18:57 EET, AI Dev Agent)
- Branch: `publish-main`
- Head commit: `4b83a30`
- Objective:
  - Fix MLX runtime health (`MLX down`) so `{hatori}` health/menu show real MLX availability and routing.
- SSOT:
  - Created issue: `mvp-factory-control#337`
    - https://github.com/moldovancsaba/mvp-factory-control/issues/337
  - Added to Project Board 1 (`MVP Factory Board`).
  - Set board fields:
    - Status: `In Progress (NOW)`
    - Product: `{hatori}`
    - Type: `Bug`
    - Priority: `P1`
  - Start note posted:
    - https://github.com/moldovancsaba/mvp-factory-control/issues/337#issuecomment-3986713125
- What changed:
  - No runtime/code fix implemented yet after trigger.
  - Executed governance/ritual updates only (SSOT + handover).
- Files touched:
  - `/Users/moldovancsaba/Projects/hatori/docs/07-runbooks/braindump-next-agent.md`
- Validation executed:
  - `git -C /Users/moldovancsaba/Projects/hatori fetch --all --prune`
  - `git -C /Users/moldovancsaba/Projects/hatori status --short --branch`
  - `git -C /Users/moldovancsaba/Projects/hatori pull --ff-only`
  - `gh project field-list 1 --owner moldovancsaba --format json`
  - `gh api graphql ... issue(number:337) { projectItems { nodes { id ... } } }`
  - `gh project item-edit ...` for Status/Product/Type/Priority
  - `gh issue comment 337 ...`
- Known risks/blockers:
  - None yet for implementation; runtime diagnosis not started after 70 trigger.
- Immediate next actions:
  1. Reproduce MLX down condition from `/v1/health`.
  2. Inspect MLX adapter healthcheck path and env resolution.
  3. Patch runtime detection/init for stable MLX up status.
  4. Validate menu output and lane routing telemetry with evidence.

## Latest learnings (session-specific)

Standing rules and gotchas live in **[docs/BRAIN_DUMP.md](../BRAIN_DUMP.md)**. Use that doc to refer to rules (e.g. `chat-no-hardcoded-answers`, `leakage-blocking`, `planning-intent-boundaries`).

- Add here only **session-specific** learnings that are not yet promoted to BRAIN_DUMP. When a learning becomes a standing rule or gotcha, add it to BRAIN_DUMP and optionally keep a one-line pointer here.

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
