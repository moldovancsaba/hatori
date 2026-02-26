# Changelog

All notable changes to this project are tracked here.

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
