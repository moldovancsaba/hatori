# Changelog

All notable changes to this project are tracked here.

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
