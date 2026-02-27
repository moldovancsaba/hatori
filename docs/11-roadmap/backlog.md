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

## Epic F — Chat UI with feedback annotations (Sprint 04)

### F1. Chat screen (`/chat`)
**Story:** As Sultan, I want a local chat timeline where I can send messages and see {hatori} replies.

**Acceptance**
- `GET /chat` renders user+assistant timeline for a `chat_id` (default `main`)
- `POST /chat/send` writes user interaction event (`source=ui`, `chat_id`)
- Assistant reply is generated via runtime/model adapter boundary and logged as assistant interaction with `related_user_interaction_id`

### F2. Assistant feedback controls
**Story:** As Sultan, I want 👍/👎 on assistant replies to become explicit learning signals.

**Acceptance**
- 👍 writes `learning_events(kind=PositiveFeedback, confidence=High, related_interaction_id=<assistant id>)`
- 👎 writes `learning_events(kind=NegativeFeedback, confidence=High/Medium, related_interaction_id=<assistant id>)`
- `details` include `vote`, `category`, `comment`, `ui_context`
- No implicit “no feedback = positive” behavior in UI

### F3. Gated promotion actions
**Story:** As Sultan, I want optional explicit promotion of feedback into Pending preferences/rules.

**Acceptance**
- UI action can create Pending PKS entries in module C or H only on explicit click
- Approval/deprecation remains in existing Pending governance flow

## Epic G — Upload + ingestion UI (Sprint 04)

### G1. Upload route (`/upload`)
**Story:** As Sultan, I want to upload local files into the system brain.

**Acceptance**
- Upload saves under `artefacts/uploads/`
- Artefact row records file path, checksum, size, and sensitivity metadata (default `Private`)
- For parseable files (`.txt`, `.md`), ingestion creates chunks + vectors
- For unsupported types (`.pdf`, `.docx` in MVP), artefact is stored with `unparsed` metadata

### G2. Search over uploaded artefacts
**Story:** As Sultan, I want uploaded files to appear in offline search with provenance.

**Acceptance**
- Search page shows snippet + artefact ID + path/checksum where available
- Retrieval remains offline/local only
