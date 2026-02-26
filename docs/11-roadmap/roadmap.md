# Roadmap

This repo implements **Hatori**, a local, offline-first, open-source personal agent with an auditable PKS and LLM-swappable runtime.

## Guiding constraints
- **Truth > fluency**
- **Offline-first degradation** (never crash; reduce claims)
- **PKS governance** (append-only logs + controlled promotion)
- **Audit trail + backups + portability**
- **Regression tests** for behavioural stability

## Phases and exit criteria

### Phase 0 — Baseline hardening (DONE-ish)
**Objective:** repeatable local environment and deterministic reset/test.

**Exit criteria**
- `make reset && make test` passes reliably
- `make run-ui` starts a local UI
- DB runs via Docker; no host `psql` required

### Phase 1 — PKS governance complete
**Objective:** memory behaves exactly like the Charter (Pending/Approved/Deprecated/Contested).

**Deliverables**
- PKS CLI supports: add/list/show/approve/deprecate/contest
- UI supports: pending queue + approve/deprecate + record detail
- Every state change writes an `audit_events` row

**Exit criteria**
- No silent overwrites; conflicts become **Contested**
- All writes are traceable via `audit_events`
- Pending is default for high-impact modules (Facts/Projects/Decisions)

### Phase 2 — Ingestion + retrieval (offline-first RAG)
**Objective:** “remember everything” without corrupting facts.

**Deliverables**
- Artefact registry + chunk storage
- Local keyword + semantic search (pgvector)
- Provenance for every retrieved snippet

**Exit criteria**
- Offline retrieval works
- Responses can cite local artefacts by stable IDs

### Phase 3 — Agent runtime loop
**Objective:** answer tasks using Charter + PKS + retrieval, while logging I/J automatically.

**Deliverables**
- Orchestrator branches on connectivity state
- Verification Ladder enforced for third-party claims
- `hatori ask` logs interaction + optional learning signals

**Exit criteria**
- Golden tests fail the system if it fabricates citations, violates offline mode, or writes memory without permission

### Phase 4 — LLM-swappable model adapter
**Objective:** swap models without losing behaviour.

**Deliverables**
- Model adapter interface (llama.cpp first)
- Consistency Check on startup/model swap

**Exit criteria**
- Model swap triggers consistency check + subset of golden tests

### Phase 5 — Ops, security, resilience
**Objective:** offline, auditable, backed up, and recoverable.

**Deliverables**
- one-command backup + restore runbooks
- export snapshots (human-readable JSON/Markdown) + DB dumps
- threat-model-driven hardening

**Exit criteria**
- backup and restore verified end-to-end

### Phase 6 — Interactive POC loop (Sprint 04)
**Objective:** deliver a usable feedback-driven chat and upload flow in the local UI.

**Deliverables**
- Chat UI route (`/chat`) with conversation timeline and send flow.
- Assistant-message feedback actions (`👍`/`👎`) writing attributable learning signals to module J.
- Upload UI route (`/upload`) for local artefacts, checksums, and ingestion into chunk/vector storage.
- UI search surface for uploaded artefacts with provenance (artefact ID + path/checksum).

**Exit criteria**
- Chat send creates user + assistant interaction events with shared `chat_id`.
- Feedback creates learning events linked to assistant interaction IDs.
- Upload of `.txt` creates artefact + embeddings rows and becomes retrievable offline.
- No silent promotion to PKS A–H from UI feedback.
