# Hatori (Local, Offline-First Agent)

## Goal
Build a long-lived personal agent ("Hatori") that:
- runs fully locally and continues operating offline,
- uses only open-source components,
- maintains an auditable, modular PKS (Personal Knowledge System),
- is LLM-swappable without losing behaviour or memory,
- learns from explicit feedback and *softly* from implicit positive outcomes.

## Non-negotiables
- Truth > fluency (no fabricated facts/sources)
- Offline-first degradation (no crash; reduced claims)
- PKS governance (append-only logs + controlled promotion to facts/preferences)
- Audit trail + backups + portability
- Regression tests for behavioural stability

## Where things live
- Charter and prompts: `docs/01-charters/`, `docs/09-prompts/`
- Architecture decisions: `docs/02-architecture/`, ADRs in `docs/08-decisions/`
- PKS spec and schema: `docs/03-data/`, `pks/`
- Ops/runbooks: `docs/04-ops/`, `docs/07-runbooks/`
  - Versioning rule: `docs/04-ops/versioning-release.md`
- Evaluation: `docs/06-evaluation/`, golden tests in `tests/golden/`
- Audit/event logs: `logs/audit/`, `logs/events/`

## Runtime MVP commands (current)
- `python -m hatori.cli ask "<question>" [--allow-pending] [--done] [--json]`
- `python -m hatori.cli ingest <path> [--json]`
- `python -m hatori.cli search "<query>" [--limit N] [--allow-pending] [--json]`
- Golden tests: `python tests/golden/run_golden.py` (also wired into `make test`)

## Offline ingest + search
- Ingest local files into `artefacts` + chunked `embeddings`:
  - `python -m hatori.cli ingest tests/golden/fixtures/offline_playbook.txt --json`
- Search merges keyword hits with semantic pgvector ranking:
  - `python -m hatori.cli search "nightly checklist" --json --limit 5`
  - `python -m hatori.cli search "car upkeep checklist" --json --limit 5`

## Embeddings design
- Adapter boundary: `hatori/embeddings.py` (`embed(texts: list[str]) -> list[list[float]]`)
- Default backend: deterministic local hash embeddings (`hash-v1`) for CI-safe offline operation.
- Optional backend: local `sentence-transformers` model from disk (`HATORI_EMBED_BACKEND=sentence-transformers`, `HATORI_EMBED_MODEL_PATH=/abs/model/path`).
- Vectors are stored in `embeddings.embedding` (`pgvector` column), with provenance in `embeddings.metadata`:
  - `path`
  - `index`
  - `embedder`
  - `embed_dim`

## Planning
- Roadmap: docs/11-roadmap/roadmap.md
- Backlog: docs/11-roadmap/backlog.md
- Sprint 01: docs/11-roadmap/sprint-01.md

## Release
- Current handoff-ready release tag: `v0.1.1`
- Verification runbook: `docs/07-runbooks/runbook-dev-handoff.md`

## Prompt Pack
- Builder system prompt: docs/09-prompts/builder-system.md
- Builder task template: docs/09-prompts/builder-task-template.md
- Runtime system prompt (minimal): docs/09-prompts/runtime-system-min.md
- Task prompt template: docs/09-prompts/task-prompt-template.md
- Memory patch format: docs/09-prompts/memory-patch-format.md
- UI runbook: docs/07-runbooks/runbook-ui.md
