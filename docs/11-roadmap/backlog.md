# Backlog

This is the actionable backlog that turns the Charter into deliverable work.

## Epic A — Governance-grade PKS

### A1. PKS record lifecycle defaults
**Story:** As Sultan, I want high-impact memories to default to **Pending** so my PKS cannot silently drift.

**Acceptance**
- `pks add` defaults to **Pending** for modules B/D/F unless explicitly overridden
- UI shows Pending queue
- Approve/Deprecate actions create `audit_events` entries

### A2. Conflict handling
**Story:** As Sultan, I want conflicts stored as **Contested** rather than overwritten.

**Acceptance**
- `pks contest <id> <reason_json>` sets status Contested
- conflict rationale stored (audit_events.details at minimum)
- no silent overwrite path exists

### A3. Memory Patch enforcement
**Story:** As Sultan, I want every proposed memory write surfaced as a **Memory Patch** before commit.

**Acceptance**
- Agent outputs a structured Memory Patch for any A–H write
- Patch can be applied via CLI/UI approve action

## Epic B — Feedback learning (J)

### B1. Explicit negative feedback
**Story:** As Sultan, I want “not satisfied” feedback to produce a Learning record and a corrective action proposal.

**Acceptance**
- CLI/UI creates `learning_events` with kind `NegativeFeedback`
- agent responses include “Learning Log (J)” section when feedback exists

### B2. Implicit positive feedback
**Story:** As Sultan, I want “no complaint” to be recorded as low-confidence positive only.

**Acceptance**
- `learning_events.kind=ImplicitPositive` uses Low confidence
- Promotions require repetition thresholds (documented)

## Epic C — Offline-first RAG

### C1. Artefact registry
**Story:** As Sultan, I want artefacts registered with stable IDs and optional checksums.

**Acceptance**
- artefacts table populated for ingested files
- checksum recorded when feasible

### C2. Chunking + embedding
**Story:** As Sultan, I want documents chunked and searchable offline.

**Acceptance**
- embeddings.content holds chunks
- embeddings.embedding (vector) populated once embedding model is selected

## Epic D — Agent runtime

### D1. Ask pipeline
**Story:** As Sultan, I want `hatori ask` to retrieve only relevant context and produce the default template.

**Acceptance**
- response includes Connectivity + Evidence + Assumptions + Actions
- no memory writes unless explicitly authorised

### D2. Verification ladder
**Story:** As Sultan, I want third-party factual claims gated by connectivity state and sources.

**Acceptance**
- OFFLINE: no web claims; verification plans only
- ONLINE-VERIFIED: citations required

## Epic E — Evaluation

### E1. Golden tests
**Story:** As Sultan, I want behaviour pinned across model swaps using tests.

**Acceptance**
- tests assert: no fabricated citations, offline gating, correct Memory Patch formatting, no inference→fact promotion
