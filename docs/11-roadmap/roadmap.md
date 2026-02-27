# Roadmap

This roadmap tracks `{hatori}` from local agent runtime to multi-integrator production hardening.

## Current Product State

- Product name: `{hatori}`
- Stable local ports:
  - UI: `23571`
  - API: `23572`
- Delivery loop in production contract:
  - ingest -> respond -> outcome (`sent_as_is` / `edited_then_sent`)
- Model gateway active:
  - per-task routing with writer/drafter/judge lanes
  - MLX + Ollama support with fallback policy

## Phase Status

## Phase 0 — Baseline Runtime (Completed)

Delivered:
- repeatable local `make up`, `make reset`, `make test`
- deterministic DB lock guard
- local UI + API service split

## Phase 1 — Governance + Auditability (Completed)

Delivered:
- governed PKS lifecycle with audit trail
- learning feedback event flow
- outcome audit table (`delivery_events`) with idempotency

## Phase 2 — Offline RAG Memory (Completed)

Delivered:
- artefact ingestion + chunking + embeddings
- offline/local retrieval with provenance
- hybrid ingest contract (`/v1/ingest/event`, `/v1/artefacts/upload`)

## Phase 3 — Integration Loop (Completed)

Delivered:
- API v1 contract for integrators
- `{reply}` loop contract: ingest/respond/outcome
- strict idempotency and replay handling (`duplicate=true`)

## Phase 4 — Service Orchestration (Completed)

Delivered:
- one-command run path (`make run`)
- macOS service/launcher support
- collision-safe startup/reuse rules

## Phase 5 — Model Routing (In Progress)

In scope:
- finalize per-task routing defaults by workload lane
- tighten quality gates for writer lane outputs
- add measurable routing telemetry by task

Exit criteria:
- stable writer lane quality under real traffic
- reproducible model bootstrap on fresh machine
- route-level health visible in `/v1/health`

## Phase 6 — Integrator Scale (Planned)

In scope:
- additional channel packs (email, whatsapp)
- stronger anti-duplication semantics for bulk ingest
- operator dashboard for loop quality (approved vs edited ratio)

Exit criteria:
- two external products integrated using same API kit
- unchanged API contract for existing integrators
- zero leakage regressions under golden tests
