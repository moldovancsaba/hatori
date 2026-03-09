# Changelog

All notable changes to this project are tracked here.

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
