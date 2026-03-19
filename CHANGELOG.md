# Changelog

All notable changes to this project are tracked here.

## [0.8.5] - 2026-03-19

### Added
- **#350 Phase 3 — optional RAG rerank:** `rerank_merged_results()` after `merge_rank_results` in `search_runtime` and `ask_runtime`. `HATORI_RERANK_MODE=off` (default) or `lexical` (token overlap on title+excerpt + original score); `HATORI_RERANK_LEXICAL_WEIGHT` (default `3.0`). Doc [RAG-rerank-phase3.md](docs/06-evaluation/RAG-rerank-phase3.md). Golden `test_113`–`test_115`.

### Changed
- RAG D5 Phase 3 marked implemented (lexical path); runbook-local env section; interfaces.md; golden count 111.

## [0.8.4] - 2026-03-19

### Added
- **#350 Phase 2:** `load_pks_context_for_reply(query)` — query-scored PKS via `retrieve_pks` + recent Approved fill; used by UI chat and API `/v1/agent/respond`. `summarize_pks_for_model` / `summarize_evidence_for_model` include `citation` for prompt JSON. Task template **Answer grounding** rules (`docs/09-prompts/task-prompt-template.md`). Golden tests `test_110`–`test_112`. `load_pks_context` SELECT now includes `id`.

### Changed
- Docs: RAG D1 reply-path note, RAG D5 Phase 2 marked done, runbook-local golden count 108, documentation-audit golden count.

## [0.8.3] - 2026-03-18

### Added
- **#350 Phase 1 — RAG retrieval eval:** `tests/rag_eval/` (`cases.json`, `run_rag_eval.py`, fixtures, README); metrics mean recall@k and MRR; `make test` runs eval after `dod_gate`, before golden; `make rag-eval` for standalone. `EVAL.run_rag_eval_suite()` in `hatori/eval.py`; interfaces.md updated. `hatori/eval.py` repo `ROOT` path fixed (`parents[1]`).

### Changed
- **runbook-local.md:** Document RAG eval step and `make rag-eval`.

## [0.8.2] - 2026-03-18

### Added
- **#350 (RAG quality) — D4–D6:** Architecture options [RAG-architecture-options-D4.md](docs/06-evaluation/RAG-architecture-options-D4.md); phased roadmap [RAG-phased-roadmap-D5.md](docs/06-evaluation/RAG-phased-roadmap-D5.md); draft follow-up GitHub issues [RAG-follow-up-issues-D6.md](docs/11-roadmap/RAG-follow-up-issues-D6.md). D1 references and DELIVERY-PLAN/issues register updated.

## [0.8.1] - 2026-03-18

### Added
- **#281 (Replay semantics):** Replay semantics doc (`docs/10-api-contracts/replay-semantics.md`); upload response `duplicate: true` on replay; golden test `test_98b_api_upload_idempotent`; API contract §7 and §8.6 updated.
- **#435 (PKS/RAG/NET/EVAL modules):** Formal modules `hatori/db.py`, `pks.py`, `rag.py`, `net.py`, `eval.py`; interfaces.md "Implemented"; golden test `test_43c_formal_modules_interface`.
- **#350 (RAG quality):** D1 codebase audit and D2 gap list (`docs/06-evaluation/RAG-retrieval-audit-D1.md`); D3 decision memo (`docs/06-evaluation/RAG-decision-memo-D3.md`).
- **Documentation/versioning/SSOT audit:** `docs/04-ops/documentation-versioning-ssot-audit.md`; doc and SSOT fixes applied.

### Changed
- **Board script:** `tools/scripts/ssot_board_update.sh` default `OWNER=@me` for user-owned GitHub projects (fixes "unknown owner type").
- **Docs:** documentation-audit.md remediated notes (interfaces implemented); LLD and DELIVERY-PLAN status updates; issues.md SSOT wording; HANDOVER card states; runbook golden count 105.

## [0.8.0] - 2026-03-18

### Fixed
- **CI import error:** `ui/app.py`: Added `from __future__ import annotations` so type hints like `dict[str, Any]` are deferred; fixes `NameError: name 'Any' is not defined` when running golden tests (e.g. `make test` in CI).
- **Chat "unsafe model output removed":** When the repair step fails (e.g. model error or empty repair), the UI now keeps the sanitized original reply if it is safe (length ≥ 20, no forbidden markers) instead of always showing the generic error. Repair is only triggered when >50% of output was removed (was 30%) to reduce false triggers on normal replies with code blocks or lists.

### Added
- **Operator dashboard (#280):** New UI route `GET /outcomes` shows sent_as_is vs edited_then_sent vs not_sent counts and approval/edit ratios for last 7 and 30 days; optional breakdown by platform and PositiveFeedback/NegativeFeedback counts. Nav link "Outcomes" added; runbook and menu-user-guide updated. No API contract change.
- **Feedback→behavior:** Recent learning_events (last 15) are summarized and injected into the chat/API task prompt as `recent_feedback_summary` (counts by kind, last negative comment, last positive note). Enables the model to adapt to user feedback without automatic PKS promotion.
- **Doc→PKS proposal:** New CLI `hatori propose-pks <path|artefact_id> [--json]` extracts 1–5 PKS candidate records (modules A–F) from a document or from an ingested artefact’s chunks using the drafter model; inserts them as **Pending** (provenance LocalDoc). User approves with `hatori pks approve <id>`.

## [0.7.9] - 2026-03-18

### Fixed
- **Golden planning tests** (test_62, test_63, test_89): NullAdapter now returns deterministic planning JSON when `HATORI_MODEL=none` and the request is Hungarian daily planning, so the golden suite passes without a live model. Assumptions include calendar/meeting wording; next_actions 5–8 items with P0/P1/P2.

## [0.7.8] - 2026-03-18

### Changed
- **SSOT verification and closure:** #337 (MLX health/menu status) and #339 (startup hardening + port defaults) verified against acceptance criteria; Done evidence posted on mvp-factory-control. #427 (API response quality) progress: test_94b_api_respond_planning_hu_quality PASS; progress note posted.
- `docs/HANDOVER.md`: Session entries for 2026-03-18 (#337 verify/close, #339 verify/close, #427 progress). Board status for #337/#339 to Done requires manual move (script GraphQL option-id limitation).

### Fixed
- **make test** now runs `make reset` first so the DB schema (including `embeddings`) is applied before golden tests; fixes "relation \"embeddings\" does not exist" when running `make test` without a prior reset.

## [0.7.7] - 2026-03-16

### Fixed
- **#337** MLX runtime health/menu status: when MLX is not configured (no `HATORI_MLX_MODEL`) or disabled (`HATORI_DISABLE_MLX=1`), health and menu now show **MLX n/a** instead of "down". `/v1/health` `runtime_status.mlx` includes `configured: false` and a clear error in those cases; menu uses `runtimeState(rt:)` for up/down/n/a.
- Chat no longer returns hardcoded daily-plan template on planning failure: exception path and empty model output now surface only error + retry guidance (e.g. start Ollama, resend); `_normalize_plan_struct` raises on empty plan instead of filling with template; bad-char check fixed (removed `""` from list that made every answer invalid).

### Changed
- `docs/BRAIN_DUMP.md` added as single referable source for operational rules and gotchas (slugs/anchors); `braindump-next-agent.md` and runbook point to it.
- `get_structured_reply` planning defaults when no overrides: minimal single-line assumption and one retry action instead of long hardcoded plan.
- API contract and menu user guide updated for `runtime_status.configured` and n/a display.

### Changed (#339 alignment)
- **Startup/stop scripts** now use documented default ports when env is unset: `UI_PORT` default 23571, `API_PORT` default 23572 (replacing legacy 8093/8094). `hatori_service.sh` and `stop_hatori.sh` source `~/.config/hatori/hatori.env` and honor configured ports; fallback defaults match `hatori_env_init.sh` and runbooks.

### Changed (#427 API response quality)
- **Planning prompt** (`generate_planning_structured`): Added explicit quality rules—natural checklist phrasing, P0/P1/P2 meaning (top outcome / today tasks / wrap-up), no repetition; for Hungarian, natural phrasing and no English section titles.
- **API chat requirements**: Added “do not repeat the user message” and “avoid awkward repetition of phrases” to generation requirements.
- **Golden test** `test_94b_api_respond_planning_hu_quality`: Asserts API planning response includes `next_actions`, no English “Next actions” in `assistant_message`, and 5–8 items when model returns full plan.

## [0.7.6] - 2026-03-02

### Added
- `POST /v1/agent/respond` now accepts `thread_context` for explicit upstream conversation context injection from `{reply}`.

### Changed
- Language selection in API respond flow now supports explicit hints from integration metadata:
  - `metadata.language_hint`
  - `metadata.identified_language`
  - `metadata.language`
- Language fallback now resolves using a strict order:
  1) explicit integration hint
  2) current message auto-detect
  3) recent `thread_context` auto-detect (for short/ambiguous messages)
- Integrated thread context is merged into prompt history before generation, improving multi-turn continuity for omnichannel callers.

### Fixed
- Reduced English fallback misfires for Hungarian conversation flows by honoring upstream identified language as deterministic fallback.

## [0.7.5] - 2026-03-02

### Fixed
- `/v1/agent/respond` now guarantees a user-sendable fallback message when:
  - local model runtime is unavailable
  - unsafe output gets removed
  - model output leaks internal scaffold/policy text (for example `I am {hatori}`, `Verification Ladder`, `No memory changes`, connectivity meta lines)
- Prevented false daily-planning routing caused by substring matching (for example `ma` inside `email`) by switching to regex-based intent detection.

### Changed
- API generation path now marks deterministic fallback executions as `standard_fallback` for easier runtime traceability.
- Shared sanitizer marker set expanded to filter known internal scaffold phrases before output reaches integration channels.

## [0.7.4] - 2026-02-28

### Added
- New end-user menu guide with segmented usage levels:
  - `docs/07-runbooks/menu-user-guide.md`
  - explicit `--- Basics ---` and `--- Advanced ---` usage paths.

### Changed
- Menu dropdown now includes visible section separators:
  - `--- Basics ---`
  - `--- Advanced ---`
- Functions are grouped by intent:
  - Basics: chat/upload/search, API health, smoke test
  - Advanced: interactions/learning inspection + service operations/logs

## [0.7.3] - 2026-02-28

### Added
- `/v1/health` now returns machine-readable runtime and routing telemetry for local monitoring:
  - `runtime_status` (MLX/Ollama availability + model info)
  - `task_model_routing` (writer/drafter/judge lane backend+model+fallback state)

### Changed
- Menu bar health panel upgraded to a mini dashboard with explicit lines for:
  - product and version (`{hatori} v<version>`)
  - runtime states (MLX/Ollama up/down)
  - writer/drafter/judge model lane status
- Existing health fields remain backward-compatible (`status`, `version`, `db`, `model`, `model_name`, ports).

## [0.7.2] - 2026-02-28

### Changed
- Menu bar app source remains fully tracked in repository under `tools/macos/HatoriMenubar/` (no core menu logic left only in compiled app artifacts).
- Menu dropdown now shows product + version header (`{hatori} v<version>`).
- Menu app installer now injects version from repository `VERSION` into both runtime menu text and app `Info.plist` (`CFBundleShortVersionString`).

## [0.7.1] - 2026-02-28

### Changed
- Enforced planning SSOT policy in docs: active roadmap/backlog/sprint execution now lives only in GitHub Project board (`moldovancsaba/projects/1`, product `{hatori}`).
- Converted `docs/11-roadmap/*` files to archived pointers (no active task queues kept in-repo).
- Updated overview and handoff docs to reference board-based planning flow only.

## [0.7.0] - 2026-02-27

### Added
- Reproducible local setup tooling for integrator teams:
  - `make bootstrap`
  - `make models-pull`
  - `make doctor`
  - `make integration-acceptance`
- Integrator acceptance runbook and API loop proofs for ingest/respond/outcome with idempotency and auth checks.
- Task-oriented model routing structure (writer/drafter/judge lanes) in runtime wiring, with documented route-level model selection.

### Changed
- Local stable service ports standardized to 5-digit range:
  - UI `23571`
  - API `23572`
- Health contract and smoke tooling aligned to configured UI/API ports.
- Menu bar and launcher docs aligned with current local web surface links.
- Documentation refresh across README, overview, roadmap, backlog, and integration docs.

### Fixed
- Stale port references in integration/client docs updated to current API port (`23572`).

## [0.6.0] - 2026-02-27

### Added
- Dedicated delivery outcome migration `pks/migrations/0002_delivery_events.sql` with auditable `delivery_events` storage and idempotency via unique `external_outcome_id`.
- Sent Outcome Feedback B-mode support on `POST /v1/agent/outcome`:
  - `original_text` and `final_sent_text` required for `edited_then_sent`
  - optional unified `diff` payload persisted as opaque text
  - linked `learning_events` plus `delivery_events` write per accepted outcome.

### Changed
- `/v1/agent/respond` response now includes `message_id` for round-trip correlation in `{reply}` outcome reporting.
- `tools/scripts/db_reset.sh` now applies all SQL migrations in order (`pks/migrations/*.sql`) to keep schema evolution deterministic.
- Local docs updated for `{reply}` outcome loop usage and unified diff examples in runbook.

## [0.5.0] - 2026-02-26

### Added
- Real local Ollama model adapter (`HATORI_MODEL=ollama`) in `hatori/model.py` using localhost endpoint `http://127.0.0.1:11434`.
- Ollama model configuration via env (`HATORI_OLLAMA_MODEL`, default `llama3.2:3b`) and adapter selection test coverage.

### Changed
- Chat generation path now supports Ollama runtime while preserving governance logging and per-message language handling.
- Launcher and runbook guidance aligned to Ollama-first local setup for fast offline operation after model pull.
- UI golden test gate remains strict (no silent dependency skips), and full UI test coverage runs in DoD/CI.

## [0.3.0] - 2026-02-26

### Added
- Chat UI route (`/chat`) with conversation timeline, message send form, and assistant response logging.
- Assistant feedback controls (`👍` / `👎`) writing attributable `learning_events` linked to assistant `interaction_events.id`.
- Upload UI route (`/upload`) storing files under `artefacts/uploads/`, recording artefact metadata/checksum, and ingesting parseable files into chunk/vector storage.
- Search UI route (`/search`) showing snippet + artefact provenance fields (artefact id, path, checksum).

### Changed
- Golden suite expanded to 50 cases, including chat/send metadata checks, feedback linkage checks, and upload ingestion/search coverage.
- UI dependency set updated to include `httpx` for UI client test coverage in CI.

## [0.2.0] - 2026-02-26

### Added
- Offline embeddings adapter boundary in `hatori/embeddings.py` with deterministic local hashing backend (`hash-v1`) and optional local `sentence-transformers` backend.
- Semantic retrieval over `pgvector` embeddings, merged with keyword retrieval for `hatori ask` and `hatori search`.
- New fixture for semantic behavior checks: `tests/golden/fixtures/semantic_garage.txt`.

### Changed
- `hatori ingest` now stores non-null vectors in `embeddings.embedding` plus embedding provenance metadata (`embedder`, `embed_dim`, source path/index).
- Golden tests expanded from 10 to 30 property-focused cases, including offline gating, pending-governance gating, memory patch gating, citation integrity, and semantic search behavior.
- Local docs/runbooks updated for offline embeddings usage, optional local dependency setup, and troubleshooting.

## [0.1.1] - 2026-02-26

### Fixed
- Added deterministic DB operation locking via atomic lock directory (`/tmp/hatori_db.lockdir`) to prevent flaky failures when DB-mutating commands run concurrently.
- Guarded `db_reset.sh`, `db_seed.sh`, `self_test.sh`, and `planning_check.sh` with shared lock handling and fail-fast contention message (`DB busy; retry`).
- Added `tools/scripts/db_lock_contention_test.sh` and wired it into `make test` to enforce lock behavior in local and CI runs.

## [0.1.0] - 2026-02-26

### Added
- Offline Runtime MVP commands in CLI:
  - `hatori ask`
  - `hatori ingest`
  - `hatori search`
- Golden test suite (`tests/golden/run_golden.py`) with 10 behavior checks.
- Fixture data for local ingestion/retrieval tests.
- Local runtime runbook updates and Sprint-01 Runtime MVP scope.
- Versioning/release hygiene policy document (`docs/04-ops/versioning-release.md`).
- CI workflow gate (`.github/workflows/ci.yml`) for push/PR:
  - `make up-ci`
  - `make reset`
  - `make test`
- Mechanical DoD gate script (`tools/scripts/dod_gate.sh`) wired into `make test`.
- Seeded Delivery Hygiene Rule in PKS + seeded audit evidence on reset.

### Fixed
- CI compatibility for `make test`: golden tests no longer require `.venv` activation and run via `python3`.
- CI startup race: `make up-ci` now waits for Postgres readiness before reset/test.

### Governance And Rules
- Added mandatory delivery hygiene rule to charter/prompts/DoD:
  - update docs
  - update `VERSION` and `CHANGELOG.md`
  - commit all changes
  - push to `origin/main`
