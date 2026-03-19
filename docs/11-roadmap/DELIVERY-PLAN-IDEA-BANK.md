# Delivery plan: {hatori} IDEA BANK issues

**Purpose:** Break down open IDEA BANK cards into deliverables, enrich context, and map a delivery plan.  
**SSOT issues:** [mvp-factory-control](https://github.com/moldovancsaba/mvp-factory-control) #281, #350, #351, #352.  
**Board:** [MVP Factory Board](https://github.com/users/moldovancsaba/projects/1) — filter Product = {hatori}.

**Status update:** #281 Done (replay semantics, upload duplicate, test_98b). #350 Backlog (SOONER); D1–D3 done (audit, gap list, decision memo); next D4–D6.

---

## 1. Issue summary and proposed order

| Order | Issue | Title | Type | Dependencies | Output |
|-------|-------|--------|------|--------------|--------|
| 1 | #281 | Bulk ingest anti-duplication | Implementation | — | Replay semantics doc + code + tests |
| 2 | #350 | RAG quality options and roadmap | Design + follow-up cards | — | Decision memo + gap list + phased roadmap + new cards |
| 3 | #351 | PII control pipeline | Design + follow-up cards | — | Architecture doc + sensitivity model + follow-up cards |
| 4 | #352 | PII-safe contact identity | Design + follow-up cards | #351 | Identity model doc + API impact + follow-up cards |

**Rationale:** #281 is self-contained and improves resilience without schema/contract change. #350 is design-first and produces implementation cards. #351 must precede #352 (contact identity builds on PII control).

---

## 2. #281 — Bulk ingest anti-duplication improvements

**SSOT:** [mvp-factory-control#281](https://github.com/moldovancsaba/mvp-factory-control/issues/281)

### Enriched context
- **Current behaviour:** Single-event ingest (`POST /v1/ingest/event`, `POST /v1/artefacts/upload`) uses `external_event_id` / `event_id` for idempotency; one event → one artefact/interaction. No defined semantics for "bulk batch" (e.g. many events in one request or many requests in a short window).
- **Goal:** When integrators send the same or overlapping events (e.g. retries, replays, backfill), ensure no duplicate writes and clear replay semantics.

### Deliverables (breakdown)
| # | Deliverable | Acceptance |
|---|-------------|------------|
| D1 | **Replay semantics doc** | Define: (a) what counts as a "bulk batch" (single batch endpoint vs N single requests); (b) idempotency key scope (per event, per batch_id, or both); (c) allowed retry behaviour (same event_id → 200 + same body, no duplicate DB rows). |
| D2 | **Single-event API behaviour** | Document and test: existing `external_event_id` / `event_id` idempotency unchanged; duplicate request returns existing IDs and 200. |
| D3 | **Bulk/batch semantics (if applicable)** | If adding a batch endpoint: define request shape, key strategy, and response (e.g. list of created/skipped per event_id). If no batch endpoint: define how N single requests must be deduplicated (e.g. by external_event_id only). |
| D4 | **Verification** | Tests or steps that prove: (1) duplicate writes do not occur under retries; (2) single-event API remains backward compatible. |

### Clarification questions (PO)
- Do we need a **batch ingest endpoint** (e.g. `POST /v1/ingest/batch` with an array of events), or is the scope limited to **hardening existing single-event ingest** so that retries and replays never create duplicates?
- Is there a concrete **integrator or scenario** (e.g. {reply} backfill, cron re-send) that we should validate against?

### Suggested board move
- Move #281 from **IDEA BANK** → **Backlog (SOONER)** when ready to implement; assign D1–D4 as checklist or sub-issues if the board supports it.

---

## 3. #350 — RAG quality improvement options and roadmap

**SSOT:** [mvp-factory-control#350](https://github.com/moldovancsaba/mvp-factory-control/issues/350)

### Enriched context
- **Current state:** Retrieval in `hatori/cli.py` (keyword + semantic pgvector); PKS and local evidence in `ui/app.py`; online snippets via SearXNG. No formal eval set; no reranker; no strict "claim → source" contract in answers.
- **Gap:** Quality of retrieval (ranking, chunking, query expansion) and of answer composition (grounding, citation) — not "RAG missing."

### Deliverables (breakdown)
| # | Deliverable | Acceptance |
|---|-------------|------------|
| D1 | **Codebase audit** | Document current retrieval path (entry points, embeddings, PKS, evidence, online); list components and data flow. |
| D2 | **Retrieval quality gap list** | Prioritised list of gaps (e.g. no rerank, no eval, weak citation in prompts). |
| D3 | **Decision memo** | Chosen path (recommendation: eval-first + answer-grounding + targeted rerank); rationale; out-of-scope. |
| D4 | **Candidate architecture options** | Short doc with 2–3 options (e.g. eval-only vs eval+rerank vs eval+grounding contract), tradeoffs, dependencies. |
| D5 | **Phased roadmap** | Phase 1: eval set + metrics. Phase 2: grounding contract or rerank (per memo). Phase 3: further tuning. |
| D6 | **Follow-up implementation cards** | Create 1–3 new issues (e.g. "RAG eval set and metrics", "Answer grounding contract") and link from #350. |

### Clarification questions (PO)
- **Scope of "local-first":** Are we allowed to add a **reranker model** (e.g. small local model or external API) or must all improvements be prompt/config only until explicitly approved?
- **Eval set:** Should the eval set be **public fixtures** in repo (e.g. `tests/rag_eval/`) or internal only?

### Suggested board move
- Keep #350 in **IDEA BANK** until D1–D3 are done (design); then move to **Backlog** or **Done** and create follow-up cards. Optionally move to **Backlog (SOONER)** if we are starting the audit now.

---

## 4. #351 — PII control pipeline before storage, indexing, and output

**SSOT:** [mvp-factory-control#351](https://github.com/moldovancsaba/mvp-factory-control/issues/351)

### Enriched context
- **Current gaps:** No PII detector/redactor; no sensitivity tags on fields; no redaction before embedding or before response. Raw content is stored and retrieved as-is.
- **Control points:** Before storage (ingest, interaction_events, learning_events); before embedding/indexing (chunks, embeddings); before response/output (API and UI responses).

### Deliverables (breakdown)
| # | Deliverable | Acceptance |
|---|-------------|------------|
| D1 | **Control architecture doc** | Where and how PII is handled: (1) inbound redaction (regex/deterministic first); (2) optional sensitivity tags per field; (3) storage shape (raw vs redacted vs policy metadata); (4) retrieval-time behaviour; (5) output guard. |
| D2 | **Field-level sensitivity model** | Which fields are "sensitive" (e.g. content, comment, original_text); schema or metadata to store sensitivity/policy. |
| D3 | **Redaction strategy** | Rules for storage / indexing / output: what is redacted, what is tokenized, what remains human-readable. |
| D4 | **Dependency and migration impact** | List of touched components (ingest, persistence, retrieval, generation); migration path (e.g. additive columns first); impact on {reply} and API contract. |
| D5 | **Follow-up implementation cards** | Create cards for implementation (e.g. "PII regex layer for ingest", "Sensitivity metadata schema") and link from #351. |

### Clarification questions (PO)
- **Regulatory scope:** Is this driven by a specific requirement (e.g. GDPR, internal policy), or best-effort reduction of PII exposure?
- **Redaction default:** Should we **redact by default** and allow opt-in "store raw" for specific flows, or **store raw** and redact only at output/retrieval until policy is fixed?

### Suggested board move
- Keep in **IDEA BANK** until architecture is chosen; then move to **Backlog** and create follow-up cards. #352 stays after #351.

---

## 5. #352 — PII-safe contact identity model

**SSOT:** [mvp-factory-control#352](https://github.com/moldovancsaba/mvp-factory-control/issues/352)

### Enriched context
- **Problem:** Messaging/email need stable identity (who is who); full redaction breaks that. We need a model where the system recognises contacts without storing raw PII in every message/chunk.
- **Depends on #351:** PII control pipeline defines where and how we store/redact; contact identity builds on that (contact_id, profile store, channel handles).

### Deliverables (breakdown)
| # | Deliverable | Acceptance |
|---|-------------|------------|
| D1 | **Recommended identity model** | Option 2 + parts of 3: canonical contact_id; contact profile store; channel handles → contact_id; message memory references contact_id. |
| D2 | **Safe-display rules** | When and how to show "safe" names/handles in UI and API; what never leaves the system. |
| D3 | **Cross-channel mapping strategy** | How channel-specific handles map to one contact_id; resolution and conflict rules. |
| D4 | **Downstream API impacts** | Changes to respond/outcome/ingest contracts if sender_id/recipient_id become contact_id or optional; {reply} and other integrators. |
| D5 | **Follow-up implementation cards** | Create cards for {hatori} (contact store, schema) and {reply} (contract changes) and link from #352. |

### Clarification questions (PO)
- **Scope of contact store:** Should contact profile and mapping live **inside {hatori}** only, or is there a shared service / {reply} ownership?
- **Timeline vs #351:** Should #352 be scheduled only after #351 implementation has started, or can design run in parallel?

### Suggested board move
- Keep in **IDEA BANK** until #351 has an agreed architecture; then move #352 to **Backlog** when ready to design identity model.

---

## 6. Board and next steps

- **Board:** Use status **Backlog (SOONER)** for "ready to work next"; **IDEA BANK** for "design or later". After this plan, suggest moving **#281** to Backlog (SOONER) and leaving #350, #351, #352 in IDEA BANK until design/answers are done, or move #350 to Backlog if we start the RAG audit.
- **This doc:** Living plan; update as deliverables are completed or new follow-up cards are created.
- **PO:** Please answer clarification questions above so implementation can proceed without ambiguity.
