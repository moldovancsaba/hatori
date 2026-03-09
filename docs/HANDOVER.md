# Handover Log

## 2026-03-03 18:29:10 EET - Codex Agent
- Branch: `publish-main`
- Base commit: `4b83a30`
- Objective: Fix startup root cause where launchd service showed API down whenever Docker/Colima was unavailable; harden launch path for smooth startup.

### What changed
- Made service bootstrap non-blocking for API/UI in `tools/scripts/hatori_service.sh`.
- Added background Docker bootstrap retry loop with lock protection and throttled logs.
- Added explicit `colima status`/`colima start` handling with failure logs.
- Updated local runbook with new startup behavior and recovery steps.
- Updated developer handoff runbook with non-blocking startup note.

### Files touched
- `tools/scripts/hatori_service.sh`
- `docs/07-runbooks/runbook-local.md`
- `docs/07-runbooks/runbook-dev-handoff.md`

### Validation
- `bash -n tools/scripts/hatori_service.sh` -> `OK_bash_syntax`
- `make install-service` -> service reinstalled and restarted
- `make service-status` with Docker down -> `API health: ok` (UI reached shortly after)
- `curl http://127.0.0.1:23572/v1/health` -> JSON `status=ok`, `db=fail` (expected degraded mode)
- `curl http://127.0.0.1:23571/chat` -> `303` (UI reachable)
- Logs show new behavior:
  - `[docker] colima start failed`
  - `[docker] stack bootstrap failed (rc=1); retry in 30s`
  - API/UI still started and listened on `23572`/`23571`

### Known issues / risks
- Colima itself remains unhealthy on this machine (outside repo): VZ/disk-attach failures still block DB container startup.
- Existing dirty working tree includes unrelated changes (e.g. `docs/07-runbooks/braindump-next-agent.md`, `READMEDEV.md` untracked); not modified here.

### Immediate next actions
1. Fix local Colima VM state (`colima stop`, `colima delete -f`, `colima start`, `docker context use colima`).
2. Verify DB recovery (`make up`, then `/v1/health` should report DB up).
3. Optionally add Docker bootstrap metrics endpoint / structured health counters for proactive alerting.

## 2026-03-03 19:04:00 EET - Codex Agent (SSOT board delivery flow)
- Branch: `publish-main`
- Objective: Ensure board updates work when product repo differs from project repo; enforce SSOT card updates for `{hatori}` delivery.

### What changed
- Confirmed SSOT issue `mvp-factory-control#339` is on board and moved to `In Progress (NOW)`.
- Added start note on SSOT card.
- Added automation script for cross-repo board updates.
- Added canonical SSOT management doc and linked it from handoff runbook.

### Files touched
- `tools/scripts/ssot_board_update.sh`
- `docs/PROJECT_MANAGEMENT.md`
- `docs/07-runbooks/runbook-dev-handoff.md`

### Validation
- `gh issue view 339 --repo moldovancsaba/mvp-factory-control --json projectItems`
  - status: `In Progress (NOW)`
- `ISSUE_NUMBER=339 ... tools/scripts/ssot_board_update.sh`
  - output: `OK: updated ... Status: In Progress (NOW), Product: {hatori}, Type: Refactor`
- `bash -n tools/scripts/ssot_board_update.sh`
  - output: syntax OK

### Known issues / follow-ups
- `moldovancsaba/hatori` has issues disabled; SSOT cards must remain in `mvp-factory-control`.
- Continue using board card `#339` for this stream until PO changes active card.

### Immediate next actions
1. Add milestone evidence comment to issue `#339` after each meaningful implementation step.
2. Use `tools/scripts/ssot_board_update.sh` at start/blocker/done cadence.
3. Close card only after DoD evidence is attached.

## 2026-03-03 19:25:00 EET - Codex Agent (MLX fallback hardening)
- Objective: add a safe operational fallback when MLX cannot be used, while preserving MLX as primary lane when healthy.

### What changed
- Added `HATORI_DISABLE_MLX` handling in model routing.
- Added `tools/scripts/hatori_mlx_mode.sh` toggle (`on|off|status`).
- Updated runbooks with explicit fallback procedure and recovery steps.
- Posted SSOT milestone evidence on card `mvp-factory-control#339`.

### Files touched
- `hatori/model.py`
- `tools/scripts/hatori_mlx_mode.sh`
- `docs/07-runbooks/runbook-local.md`
- `docs/07-runbooks/menu-user-guide.md`

### Validation
- `tools/scripts/hatori_mlx_mode.sh off` + service restart:
  - `/v1/health` shows writer `backend=ollama`, `fallback_used=true`.
- `tools/scripts/hatori_mlx_mode.sh on` + `launchctl kickstart -k gui/$(id -u)/com.hatori`:
  - API env shows `HATORI_DISABLE_MLX=0`.
  - `/v1/health` shows writer `backend=mlx`, `fallback_used=false`.

### Known issues
- Docker/Colima remains unhealthy on host, so DB stays degraded (`db=fail`) until VM is repaired.

### Next actions
1. Finalize DoD evidence bundle for card #339.
2. If requested, add a tiny test for `HATORI_DISABLE_MLX` routing behavior.

## 2026-03-06 13:22:32 CET - Codex Agent (SearXNG online routing)
- Branch: `publish-main`
- Base commit: `4b83a30`
- Objective: Replace ad-hoc online handlers with a simple routed online path (SearXNG retrieval + local LLM synthesis), with operational controls for reliable startup/use.

### What changed
- Added SearXNG-first retrieval adapter in chat online routing (`ui/app.py`), with DuckDuckGo/Wikipedia fallback.
- Added SearXNG loopback headers (`X-Forwarded-For`, `X-Real-IP`) to satisfy default botdetection rules.
- Added auto online routing mode helper (`HATORI_ONLINE_ROUTE_MODE=auto|keyword|off`).
- Added lightweight lane selection for online synthesis (`retrieval_query_build`) to reduce latency compared to writer/MLX lane.
- Added SearXNG ops scripts and Make targets:
  - `tools/scripts/searxng_up.sh`
  - `tools/scripts/searxng_down.sh`
  - `tools/scripts/searxng_status.sh`
  - `make searxng-up|down|status`
- Updated env bootstrap defaults for online routing and SearXNG endpoint.
- Updated local runbook with online routing startup/use instructions.
- Updated SSOT card `mvp-factory-control#339` note and kept status `In Progress (NOW)`.

### Files touched
- `ui/app.py`
- `tools/scripts/searxng_up.sh`
- `tools/scripts/searxng_down.sh`
- `tools/scripts/searxng_status.sh`
- `tools/scripts/hatori_env_init.sh`
- `Makefile`
- `docs/07-runbooks/runbook-local.md`

### Validation
- `python3 -m py_compile ui/app.py` -> pass
- `make searxng-up` -> container started (`hatori-searxng`)
- `make searxng-status` -> `status: ok`
- `curl -H 'X-Forwarded-For: 127.0.0.1' -H 'X-Real-IP: 127.0.0.1' 'http://127.0.0.1:8888/search?q=latest+OpenAI+news&format=json'` -> JSON results returned
- `.venv/bin/python -c 'from ui.app import online_search_snippets; print(len(online_search_snippets(\"latest OpenAI news\",3)))'` -> non-zero hits
- `ISSUE_NUMBER=339 ... tools/scripts/ssot_board_update.sh` -> project item updated + milestone note posted

### Known issues / risks
- SearXNG default container currently reports no explicit `docker ps` row in the custom status table grep output format even when healthy; probe status remains authoritative.
- API `/v1/health` can still feel slow intermittently because health currently includes runtime checks that can block.

### Immediate next actions
1. Add dedicated `/v1/health/quick` endpoint (no heavy runtime checks) and switch menubar probe to quick health.
2. Add chat-timeout guard for long model generations in online mode (return partial sourced summary if model exceeds timeout).
3. If PO wants strict “SearXNG only”, disable external fallbacks in `online_search_snippets`.

### Addendum (2026-03-06 13:27 CET)
- Switched `HATORI_ONLINE_SYNTHESIS_MODE` default to `direct` to avoid long waits on heavy local model lanes for online queries.
- Verified chat E2E: POST `/chat/send` with `what is the latest OpenAI news?` returned `303`, then chat view showed assistant text starting with `I found live web results for:`.
- Updated SSOT issue #339 with this milestone evidence.

## 2026-03-07 11:54:54 CET - Codex Agent (Idea Bank planning: RAG + PII)
- Branch: `publish-main`
- Base commit: `4b83a30`
- Objective: Create Idea Bank SSOT cards for RAG quality improvements and PII/privacy architecture, including contact identity and `{reply}` API dependencies.

### What changed
- Created four new SSOT issues in `moldovancsaba/mvp-factory-control`.
- Added all four cards to Project #1 and set them to `IDEA BANK`.
- Updated active tracking card `#339` with a start note for this planning pass.

### Files touched
- `docs/HANDOVER.md`

### Validation
- `gh issue view 350 --json projectItems` -> `IDEA BANK`
- `gh issue view 351 --json projectItems` -> `IDEA BANK`
- `gh issue view 352 --json projectItems` -> `IDEA BANK`
- `gh issue view 353 --json projectItems` -> `IDEA BANK`

### Known issues / risks
- No implementation started from these cards yet.
- Existing repo worktree remains dirty and uncommitted from earlier sessions.

### Immediate next actions
1. Decide whether PII phase 1 should be deterministic-only or deterministic + metadata schema.
2. Decide whether to keep current contact storage model or move to canonical `contact_id` mapping.
3. Break the selected Idea Bank card into Ready/Next implementation cards.

## 2026-03-07 12:06:56 CET - Codex Agent (70 protocol handoff)
- Branch: `publish-main`
- Base commit: `4b83a30`
- Objective: Capture planning state for RAG/PII/contact-identity work and hand off with verified SSOT references.

### What changed
- Executed 70 protocol SSOT update on active card `#339`.
- Confirmed Idea Bank cards remain the current planning outputs:
  - `#350` RAG quality roadmap
  - `#351` PII control pipeline
  - `#352` PII-safe contact identity model
  - `#353` cross-system sensitivity/redaction API contract
- No implementation from these cards started yet.

### Files touched
- `docs/HANDOVER.md`

### Validation
- `gh issue view 350 --repo moldovancsaba/mvp-factory-control --json projectItems` -> `IDEA BANK`
- `gh issue view 351 --repo moldovancsaba/mvp-factory-control --json projectItems` -> `IDEA BANK`
- `gh issue view 352 --repo moldovancsaba/mvp-factory-control --json projectItems` -> `IDEA BANK`
- `gh issue view 353 --repo moldovancsaba/mvp-factory-control --json projectItems` -> `IDEA BANK`
- `ISSUE_NUMBER=339 ... tools/scripts/ssot_board_update.sh` -> active card updated with 70 note

### Known issues / risks
- The repo worktree remains dirty from earlier implementation sessions and planning updates.
- README/version/commit/push/final release hygiene for earlier code changes are still not completed.

### Immediate next actions
1. Select phase-1 PII architecture: deterministic-only vs deterministic + sensitivity metadata.
2. Select contact identity direction: raw-contact-compatible vs canonical `contact_id` mapping.
3. Convert the selected Idea Bank card(s) into `Ready (NEXT)` implementation cards with acceptance criteria and dependency ordering.

## 2026-03-09 10:25:00 CET - Codex Agent (Menubar Harmonization & Icons)
- Branch: `publish-main`
- Objective: Harmonize macOS menu bar apps, implement custom icons, and auto-launch capabilities.

### What changed
- Harmonized all 3 macOS menu bar apps (ReplyMenubar, HatoriMenubar, OpenClawMenubar).
- Globally renamed "toolbar" terminology to "menubar".
- Generated multi-resolution `.icns` native macOS application icons and bundled them.
- Updated installation scripts to remove old toolbars and register new apps to Login Items via `osascript`.
- Issue `mvp-factory-control#362` verified and marked Done.

### Files touched
- `tools/macos/HatoriMenubar/install_menubar_app.sh`
- `tools/macos/HatoriMenubar/ToolbarCore.swift`
- `docs/HANDOVER.md`

### Validation
- All three apps compiled, uninstalled old toolbars safely, and registered themselves to start at login seamlessly.
- GH issue 362 closed.
