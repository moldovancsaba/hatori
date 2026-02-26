# Developer Handoff Runbook

This runbook is for onboarding a developer/developer-agent to the Hatori repo.

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
- no unexpected merge conflicts

```bash
make up
./tools/scripts/planning_check.sh
```
Expected final lines:
- `PASS: self_test`
- `PASS: dod_gate`
- `PASS: golden tests (10 cases)`
- `UI app present: True`
- `OK: planning check complete`

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
