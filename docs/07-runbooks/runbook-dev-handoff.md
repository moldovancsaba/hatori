> Planning SSOT: active roadmap/backlog/sprint items live only on https://github.com/users/moldovancsaba/projects/1 (Product `{hatori}`).

# Developer Handoff Runbook

This runbook is for onboarding a developer/developer-agent to the Hatori repo.

## Current handover snapshot
- Active branch: `sprint-05-daily-planning-golden`
- Head commit: `c86928b`
- Open PR: https://github.com/moldovancsaba/reply-hatori/pull/4
- Latest CI run: https://github.com/moldovancsaba/reply-hatori/actions/runs/22484817404
- Dedicated ports:
  - UI: `8093` (localhost)
  - API: `8094` (localhost)
- Continuation notes: `docs/07-runbooks/braindump-next-agent.md`

## Repo
- Path (local): `/Users/moldovancsaba/Projects/reply-hatori`

## Canonical policy & prompts
- Charter (highest authority): `docs/01-charters/hatori-charter-v3.md`
- Prompt pack: `docs/09-prompts/`
  - `builder-system.md`
  - `builder-task-template.md`
  - `runtime-system-min.md`
  - `task-prompt-template.md`
  - `memory-patch-format.md`

## Prerequisites
- macOS + Apple Silicon supported (arm64)
- `brew` installed
- `colima` installed (or other Docker daemon)
- `docker` CLI available

## Start Docker runtime (Colima)
```bash
colima start
docker context use colima
docker ps
```

## Bring up Hatori DB container
```bash
cd /Users/moldovancsaba/Projects/reply-hatori
make up
```

## One-command health check
```bash
cd /Users/moldovancsaba/Projects/reply-hatori
./tools/scripts/planning_check.sh
```
Expected end state:
- `OK: Postgres reachable (hatori-pg)`
- `PASS: self_test`
- `UI app present: True`
- `OK: planning check complete`

## Verification Evidence Pack (Delivery Hygiene Rule)

Run in order:

```bash
cd /Users/moldovancsaba/Projects/reply-hatori
git pull --ff-only
git status -sb
```
Expected:
- branch up to date with `origin/main`
- working tree clean (`## main...origin/main` with no `M` or `??` lines)

```bash
make up
./tools/scripts/planning_check.sh
```
Expected final lines:
- `PASS: self_test`
- `PASS: dod_gate`
- `PASS: golden tests (89 cases)`
- `UI app present: True`
- `OK: planning check complete`

Sprint 04 chat/upload verification:
```bash
PORT=8093 make run-ui-hatori
curl -s -o /dev/null -w "GET_CHAT_HTTP=%{http_code}\n" http://127.0.0.1:8093/chat
curl -s -o /dev/null -w "POST_CHAT_SEND_HTTP=%{http_code}\n" -X POST http://127.0.0.1:8093/chat/send -d "chat_id=proof-chat&message=hello" -H "Content-Type: application/x-www-form-urlencoded"
curl -s -o /dev/null -w "POST_UPLOAD_HTTP=%{http_code}\n" -F "file=@tests/golden/fixtures/upload_note.txt;type=text/plain" http://127.0.0.1:8093/upload
```
Expected:
- `GET_CHAT_HTTP=200`
- `POST_CHAT_SEND_HTTP=303`
- `POST_UPLOAD_HTTP=200`
- DB rows exist for `interaction_events` (`chat_id=proof-chat`), linked `learning_events` after feedback, and uploaded artefact + embeddings.

Lock behavior note:
- DB-mutating checks use an atomic lock directory (`/tmp/hatori_db.lockdir`).
- If a second DB-mutating command starts concurrently, it fails fast with `DB busy; retry`.
- Official DoD commands are sequential (do not run `planning_check.sh` and `make test` at the same time).

```bash
./tools/scripts/hatori pks show 0c942328-f2cb-4293-8a7e-9c0574d51301
```
Expected:
- row contains `|H|Approved|Delivery Hygiene Rule|`

```bash
./tools/scripts/db_psql.sh -c "select occurred_at, actor, action, target_type, target_id, details from audit_events where target_id='0c942328-f2cb-4293-8a7e-9c0574d51301' order by occurred_at desc limit 5;"
```
Expected:
- at least one row with `target_type = pks_record`
- `target_id = 0c942328-f2cb-4293-8a7e-9c0574d51301`

## Run UI (local dashboard)
Prereq: venv created and deps installed (see `ui/requirements.txt`).
```bash
cd /Users/moldovancsaba/Projects/reply-hatori
make run-ui
```
Open:
- `http://127.0.0.1:8088`

Stop:
- `Ctrl+C`

## Common recovery actions
### DB container not running
```bash
docker ps -a --format '{{.Names}}' | grep -qx hatori-pg && docker start hatori-pg
```

### Full reset (DB schema + seed)
```bash
cd /Users/moldovancsaba/Projects/reply-hatori
make reset
make test
```

### Colima disk-in-use error
Recreate the VM:
```bash
colima stop || true
colima delete -f || true
colima start
docker context use colima
```

## Definition of Done for Sprint 01
Sprint 01 focuses on governance + usability:

1) UI: approve/deprecate **reason capture** stored into `audit_events.details`
2) UI: PKS detail page `/pks/<uuid>` (review body before approval)
3) UI: export-to-disk snapshot under `artefacts/exports/` + create `artefacts` row
4) CLI: PKS state changes (approve/deprecate/contest) must also write `audit_events`
5) Delivery hygiene (mandatory for every task):
   - update affected documentation/runbooks
   - update versioning artefacts (`VERSION` and `CHANGELOG.md`)
   - commit all task changes
   - push to `origin/main`

All changes must preserve:
- `make up`
- `make reset`
- `make test`
- `make run-ui`
- `./tools/scripts/planning_check.sh`

## Next-agent continuation prompt
Use this prompt as-is for the next developer agent:

```text
You are a developer agent working on repo:
  /Users/moldovancsaba/Projects/reply-hatori
Remote:
  https://github.com/moldovancsaba/reply-hatori.git
Branch to continue:
  sprint-05-daily-planning-golden
Baseline commit:
  c86928b

Mission: stabilize API response quality for `{reply}` integration while preserving governance and leakage protections.

Hard requirements:
1) Keep API contract and auth unchanged (`/v1/*`, `X-Hatori-Token`, `HATORI_API_TOKEN`).
2) Keep localhost-only binding and port separation (`UI 8093`, `API 8094`).
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
- curl health/respond/feedback/search proofs on :8094

Deliverables:
- PR URL + green CI URL
- sample API respond output from DB (clean + useful Hungarian)
- summary of files changed
```
