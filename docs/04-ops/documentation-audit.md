# Documentation vs. Code Audit

**Date:** 2026-03-18  
**Scope:** All `docs/` and key code paths; consistency and implementation stage of core functions.

---

## 1) Executive summary

- **Several docs describe behaviour or modules that do not match the code:** Model Gateway (separate module, circuit breaker, generator order), interfaces (PKS/RAG as formal modules), runbook UI port/target, and golden test count.
- **Referenced doc paths that do not exist:** `docs/03-data/`, `docs/06-evaluation/`.
- **Core behaviour is implemented** (API, UI, CLI, model routing, embeddings, RAG, learning loop, outcomes) but **not** behind the abstract interfaces documented in `interfaces.md`; circuit breaker and `model_gateway.py` are **not implemented**.

Recommended: fix or remove outdated references, align overview/README with actual code (model routing, no circuit breaker, no `model_gateway.py`), add missing doc placeholders or content, and treat `interfaces.md` as target design rather than current implementation.

---

## 2) Inconsistencies (doc vs code)

### 2.1 Model Gateway and generator routing

| Doc | Says | Code reality |
|-----|------|--------------|
| `docs/00-overview/README.md` § "Model Gateway (generator routing)" | Internal gateway module: **`hatori/model_gateway.py`**. Stable interface: `generate(prompt, opts) -> GatewayResult`, `embed(texts, opts) -> EmbeddingResult`. Default **`HATORI_GENERATOR_ORDER=mlx,ollama`**. **Circuit breaker:** process-local breaker skips failing backends; breaker state in **`/v1/health`**. | **No `hatori/model_gateway.py`.** Routing lives in **`hatori/model.py`**: `get_model_adapter()`, `get_task_model_adapter(task)` with **task-based** routing (`HATORI_ROUTE_<TASK>_BACKEND/MODEL/FALLBACK_*`). No `GatewayResult`/`EmbeddingResult` types. **No circuit breaker** in API or model layer; health only probes current adapter state. `HATORI_GENERATOR_ORDER` appears only in **Makefile/scripts** (e.g. `ensure_ollama.sh`, `hatori_env_init.sh`) for *script* logic, not in Python. |

**Severity:** High — overview describes a non-existent module and a non-existent feature (circuit breaker).

**Recommendation:** Rewrite the "Model Gateway" section to describe **`hatori/model.py`**: task-based routing, `get_task_model_adapter(task)`, per-task env vars, primary/fallback, and that health exposes **runtime_status** and **task_model_routing** (no breaker). Optionally document `HATORI_GENERATOR_ORDER` as script-level hint only.

---

### 2.2 Health response shape

| Doc | Says | Code reality |
|-----|------|--------------|
| `docs/10-api-contracts/hatori-api-v1.md` § 8.1 | Lists `status`, `version`, `ui_port`, `api_port`, `db`, `model`, `model_name`, `request_counts_last_minute`, `runtime_status`, `task_model_routing`. | API also returns **`ok`**, **`statusMessage`** (e.g. `"online"`). Contract does not list these. |

**Severity:** Low — extra fields are additive; clients that ignore unknown keys are fine.

**Recommendation:** Add `ok` and `statusMessage` to the contract, or explicitly state "additional fields may be present".

---

### 2.3 UI runbook (port and run target)

| Doc | Says | Code reality |
|-----|------|--------------|
| `docs/07-runbooks/runbook-ui.md` | Run: `make run-ui`. Open: **http://127.0.0.1:8088** | **`make run-ui`** runs UI on **8088** (hardcoded in Makefile). **`make run`** and service use **`make run-ui-hatori`**, which uses **`UI_PORT`** (default **23571**). Main flow is 23571; 8088 is legacy/dev-only. |

**Severity:** Medium — runbook describes a different port and target than the main "Run Modes" in overview/README.

**Recommendation:** State that `make run-ui` is dev-only (port 8088); for full stack and service use `make run` / `make run-ui-hatori` (port 23571 from env). Or merge runbook-ui into runbook-local and drop 8088 as primary.

---

### 2.4 Golden test count

| Doc | Says | Code reality |
|-----|------|--------------|
| `docs/07-runbooks/runbook-local.md` | "50 golden tests" → "100+ golden tests" (remediated) | **111** tests in golden suite (collect_tests). |

**Severity:** Low.

**Recommendation:** Replace "50" with "100+ golden tests" or "run_golden.py golden suite".

---

### 2.5 PKS / RAG as formal modules (interfaces.md)

| Doc | Says | Code reality |
|-----|------|--------------|
| `docs/10-api-contracts/interfaces.md` | **PKS:** `PKS.append_interaction`, `PKS.log_learning`, `PKS.write_pending`, `PKS.approve/deprecate/redact`, `PKS.query`. **RAG:** `RAG.index_document`, `RAG.search_local`, `RAG.get_sources`. **Connectivity:** `NET.status()`. **Evaluation:** `EVAL.run_golden_tests`. | **No such modules.** Interactions: direct SQL / `insert_interaction` in `ui/app.py` and `api/app.py`. Learning: `insert_learning` in ui/api/cli. PKS: CLI `hatori pks approve/deprecate`, UI `/pks/*` routes, direct SQL. RAG: chunk/embed in `api/app.py` and `ui/app.py`; search in `hatori/cli.py` (`retrieve_embeddings`, `retrieve_embeddings_semantic`, `retrieve_pks`, `merge_rank_results`) and UI `load_local_evidence_context` / API search path. No `NET.status()`; connectivity is env-derived (e.g. `connectivity_state()` in cli). Golden: `tests/golden/run_golden.py` (no EVAL module). |

**Severity:** High for "implementation contract" interpretation — code did not implement these interfaces at audit time.

**Status (remediated):** Implemented as discrete modules in `hatori/`: `hatori.pks`, `hatori.rag`, `hatori.net`, `hatori.eval`, `hatori.db`. interfaces.md updated to "Implemented". See LLD-documentation-audit-remediation.md and #435.

---

## 3) Missing or wrong doc references

| Reference | Location | Issue |
|-----------|----------|--------|
| **PKS spec and schema: `docs/03-data/`, `pks/`** | `docs/00-overview/README.md` § "Where things live" | **`docs/03-data/` does not exist.** `pks/` exists (migrations only: `0001_init.sql`, `0002_delivery_events.sql`). |
| **Evaluation: `docs/06-evaluation/`, golden tests in `tests/golden/`** | Same section | **`docs/06-evaluation/` does not exist.** Golden tests live in `tests/golden/run_golden.py`. |

**Recommendation:** Remove or replace references to `docs/03-data/` and `docs/06-evaluation/`. Options: (a) add minimal placeholder READMEs under `docs/03-data/` and `docs/06-evaluation/` pointing to schema in `pks/migrations/` and to `tests/golden/run_golden.py`, or (b) change overview to "PKS schema: `pks/migrations/`" and "Evaluation: golden tests in `tests/golden/`" without pointing to missing dirs.

---

## 4) Duplicate / redundant blocks in overview

**Location:** `docs/00-overview/README.md`

- The sections **"Planning (SSOT)"**, **"Release"**, **"API Contract"**, and **"Prompt Pack"** appear **twice** (once after "Model Gateway" and again at the end). Same text repeated.

**Recommendation:** Keep a single instance of each; remove the duplicate block.

---

## 5) Core functions — implementation stage

What is **actually implemented** vs documented.

### 5.1 API (api/app.py)

| Capability | Implemented | Notes |
|------------|-------------|--------|
| `GET /v1/health` | ✅ | Returns version, db, model, model_name, runtime_status, task_model_routing, request_counts_last_minute, ok, statusMessage. |
| `POST /v1/agent/respond` | ✅ | Idempotency via external_request_id; language detection; thread_context; calls UI for reply generation and inserts user/assistant interactions. |
| `POST /v1/agent/feedback` | ✅ | Writes learning_events; token required. |
| `POST /v1/agent/outcome` | ✅ | Idempotency via external_outcome_id; delivery_events + learning_events; sent_as_is / edited_then_sent / not_sent. |
| `POST /v1/ingest/event` | ✅ | Idempotency via external_event_id; content size limit; writes interaction_events. |
| `POST /v1/artefacts/upload` | ✅ | Multipart; chunk + embed; idempotent by external_event_id. |
| `POST /v1/artefacts/ingest_path` | ✅ | Guarded by HATORI_ALLOW_PATH_INGEST and allowlist. |
| `GET /v1/search` | ✅ | Token required; uses UI search/evidence helpers; returns snippets, source, title, path, score. |
| Rate limits | ✅ | In-memory, token-scoped; configurable via env. |
| Auth | ✅ | X-Hatori-Token; health public, rest require token. |

**Stage:** **Complete** for v1 contract (no WebSocket). Contract and implementation aligned except extra health fields.

---

### 5.2 UI (ui/app.py)

| Capability | Implemented | Notes |
|------------|-------------|--------|
| `/`, `/chat`, `/chat/new`, `/chat/archive` | ✅ | Chat history and session handling. |
| `POST /chat/send` | ✅ | Reply generation; drafter (context_pack) + writer (reply_write or plan_write); repair/sanitization; learning_events on feedback. |
| `POST /chat/feedback` | ✅ | Thumbs up/down → learning_events. |
| `/upload`, `POST /upload` | ✅ | File upload → artefacts + chunks + embeddings. |
| `/search` | ✅ | RAG search (PKS + embeddings), keyword + semantic. |
| `/interactions`, `/learning` | ✅ | List views. |
| `/outcomes` | ✅ | Operator dashboard: 7d/30d counts, approval/edit %, platform breakdown; uses delivery_events + learning_events. |
| `/pks/pending`, `/pks/all`, `/pks/{rid}`, `POST /pks/approve`, `POST /pks/deprecate` | ✅ | PKS management. |
| `/export.json`, `POST /export/disk` | ✅ | Export. |
| Online search (SearXNG) | ✅ | Optional; env-driven; synthesis mode. |
| Weather / offline fallbacks | ✅ | Env and connectivity state. |

**Stage:** **Complete** for current feature set. Runbook and LLD-280 align with `/outcomes` and operator dashboard.

---

### 5.3 CLI (hatori/cli.py)

| Command | Implemented | Notes |
|---------|-------------|--------|
| `ask` | ✅ | Uses model adapter; PKS + evidence context; optional --allow-pending, --done, --json. |
| `ingest` | ✅ | Chunk + embed; artefacts + embeddings. |
| `propose-pks` | ✅ | Extracts PKS candidates; inserts Pending (LocalDoc). |
| `pks approve` / `pks deprecate` | ✅ | Status updates. |
| `search` | ✅ | Merges PKS + keyword + semantic retrieval; --limit, --allow-pending, --json. |
| `consistency-check` | ✅ | --subset, --json. |
| `model-smoke` | ✅ | Smoke test for configured model. |
| `ping`, `log`, `feedback` | ✅ | DB and learning helpers. |

**Stage:** **Complete** vs overview list. No discrepancy.

---

### 5.4 Model layer (hatori/model.py)

| Capability | Implemented | Notes |
|------------|-------------|--------|
| Adapters: Null, Ollama, LlamaCpp, MLX | ✅ | All have `generate(system_prompt, task_prompt)` and `healthcheck()`. |
| Task-based routing | ✅ | `get_task_model_adapter(task)`; env `HATORI_ROUTE_<TASK>_BACKEND/MODEL/FALLBACK_BACKEND/FALLBACK_MODEL`. |
| Default routes | ✅ | reply_write, plan_write, rewrite_polish, classify_intent, extract_fields, context_pack, retrieval_query_build, edit_pattern_cluster, answer_score, quality_gate with sensible defaults (e.g. granite4:350m for drafter-style tasks, gemma fallback). |
| Legacy single-model mode | ✅ | `HATORI_MODEL` forces one adapter for all tasks; `prefer_ollama_if_available()` fallback when no route configured. |
| Labels for health/menu | ✅ | In api/app.py: _MODEL_LABELS (e.g. Granite Nano); task_model_routing exposes model_primary, model_label. |

**Stage:** **Complete**. No `model_gateway.py`; no circuit breaker; no `HATORI_GENERATOR_ORDER` in Python — routing is task-based in this file.

---

### 5.5 Embeddings (hatori/embeddings.py)

| Capability | Implemented | Notes |
|------------|-------------|--------|
| Adapter interface | ✅ | `embed(texts: list[str]) -> list[list[float]]`; used by API ingest and UI. |
| Hash backend (default) | ✅ | Deterministic, CI-friendly. |
| Sentence-transformers backend | ✅ | Optional; HATORI_EMBED_BACKEND, HATORI_EMBED_MODEL_PATH. |

**Stage:** **Complete** and matches overview "Embeddings design".

---

### 5.6 RAG / retrieval

| Capability | Implemented | Notes |
|------------|-------------|--------|
| Chunking | ✅ | ui.app chunk_text; used in API and UI upload. |
| Indexing (artefacts + embeddings) | ✅ | API upload/ingest_path; UI upload; CLI ingest. |
| Search: keyword + semantic | ✅ | cli: retrieve_embeddings (keyword), retrieve_embeddings_semantic (vector); merge_rank_results. |
| PKS retrieval | ✅ | cli retrieve_pks; UI load_pks_context; API/UI use for respond context. |
| Evidence for reply | ✅ | UI load_local_evidence_context; API respond uses same via UI helpers. |

**Stage:** **Complete** for current RAG flow. Implemented as direct DB/helpers, not as a single RAG module.

---

### 5.7 Learning and outcomes

| Capability | Implemented | Notes |
|------------|-------------|--------|
| learning_events | ✅ | Feedback (thumbs), outcome (sent_as_is → PositiveFeedback; edited_then_sent → NegativeFeedback; not_sent → Neutral). |
| delivery_events | ✅ | Idempotent by external_outcome_id; stores assistant_interaction_id, status, original/final text, diff. |
| recent_feedback_summary for model | ✅ | summarize_recent_learning_for_model; injected into respond/chat context. |

**Stage:** **Complete** and aligned with overview "Annotate knowledge" and BRAIN_DUMP wrong-answer-better-than-none.

---

### 5.8 Not implemented (documented elsewhere)

| Documented | Implementation |
|------------|----------------|
| **Circuit breaker** (overview) | Not in code. Health does not expose breaker state. |
| **`hatori/model_gateway.py`** (overview) | File does not exist. |
| **PKS/RAG/NET/EVAL modules** (interfaces.md) | **Remediated:** Implemented as `hatori/pks.py`, `rag.py`, `net.py`, `eval.py`, `db.py` (#435). |

---

## 6) Recommended action list

1. **Overview (00-overview/README.md)**  
   - Replace "Model Gateway" section with accurate description of **hatori/model.py** (task routing, no gateway module, no circuit breaker).  
   - Remove or fix references to `docs/03-data/` and `docs/06-evaluation/`.  
   - Remove duplicate "Planning (SSOT)", "Release", "API Contract", "Prompt Pack" block.

2. **API contract (hatori-api-v1.md)**  
   - Document optional health fields `ok`, `statusMessage` or allow "additional fields".

3. **Runbook UI (runbook-ui.md)**  
   - Clarify that `make run-ui` is dev-only (port 8088); primary flow is `make run` / run-ui-hatori (23571).

4. **Runbook local (runbook-local.md)**  
   - Update golden test count to "100+ golden tests" or "golden suite in tests/golden/run_golden.py".

5. **Interfaces (interfaces.md)**  
   - **Done.** interfaces.md now states "Implemented" and lists hatori.pks, rag, net, eval.

6. **Optional**  
   - Add `docs/03-data/README.md` and `docs/06-evaluation/README.md` as short placeholders linking to `pks/migrations/` and `tests/golden/`, or remove those paths from overview.

---

## 7) Doc-to-code map (quick reference)

| Topic | Primary doc | Primary code |
|------|-------------|--------------|
| API v1 | docs/10-api-contracts/hatori-api-v1.md | api/app.py |
| UI routes (chat, upload, search, outcomes, PKS) | runbook-local, LLD-280, menu-user-guide | ui/app.py |
| Model routing | docs/00-overview (to fix), api contract §8.1, §13 | hatori/model.py, api/app.py _runtime_status, _task_routing_status |
| Embeddings | docs/00-overview § Embeddings design | hatori/embeddings.py, api/app.py, ui/app.py |
| CLI | docs/00-overview § Runtime MVP commands | hatori/cli.py |
| PKS schema | pks/migrations/ | pks/migrations/0001_init.sql, 0002_delivery_events.sql |
| Learning / outcomes | docs/00-overview, BRAIN_DUMP, LLD-280 | api/app.py, ui/app.py (insert_learning, delivery_events, outcomes) |
| Integration acceptance | docs/12-reply-integration/integration-acceptance.md | tools/scripts/integration_acceptance.sh |
