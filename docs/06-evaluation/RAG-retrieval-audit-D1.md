# RAG / retrieval path — codebase audit (D1 for #350)

**Purpose:** Document current retrieval entry points, components, and data flow for RAG quality work.  
**Issue:** [mvp-factory-control#350](https://github.com/moldovancsaba/mvp-factory-control/issues/350).

---

## 1) Entry points

| Entry point | Location | Triggers retrieval? | Notes |
|-------------|----------|---------------------|--------|
| **UI chat** | `ui/app.py` → `chat_send()` | Yes | `load_pks_context(6)`, `load_local_evidence_context(query, 5)` |
| **API respond** | `api/app.py` → `_generate_reply()` | Yes | Same: `ui.load_pks_context(6)`, `ui.load_local_evidence_context(message, 5)` |
| **CLI ask** | `hatori/cli.py` → `ask_runtime()` | Yes | `retrieve_pks`, `retrieve_embeddings`, `retrieve_embeddings_semantic`, `merge_rank_results` → evidence |
| **UI search page** | `ui/app.py` → `search()` (GET) | Yes | `search_runtime(q, limit, allow_pending=False)` |
| **API search** | `api/app.py` → `search()` | Yes | `ui.search_runtime(q, k, allow_pending=False)` |
| **RAG module** | `hatori/rag.py` | Yes | `search_local()` delegates to `cli.search_runtime()`; `index_document()` to `cli.ingest()` |

---

## 2) Data flow (UI/API reply path)

1. **User message** (UI form or API `POST /v1/agent/respond` body).
2. **PKS context (reply path):** `load_pks_context_for_reply(query, limit=6)` in `ui/app.py` → `retrieve_pks(query)` (keyword-scored Approved rows) first, then fill with recent Approved not already included. Legacy `load_pks_context` (recent-only) remains for non-reply use.
3. **Local evidence:** `load_local_evidence_context(query, limit=5)` → calls `hatori.cli.search_runtime(query, limit, allow_pending=False)`.
4. **search_runtime** (`hatori/cli.py`):
   - `retrieve_pks(question, allow_pending, limit)` — keyword score over title+body (tokenize + `score_text`), up to 400 PKS rows, return top `limit`.
   - `retrieve_embeddings(question, limit)` — keyword score over last 800 embedding rows (no vector search in this path for “keyword” branch; name is legacy).
   - `retrieve_embeddings_semantic(question, limit)` — embed query via `hatori.embeddings` adapter, pgvector `<=>` distance, filter by term overlap and score ≥ 0.30, return top `limit`.
   - `merge_rank_results(pks_hits + emb_kw_hits + emb_sem_hits, limit)` — dedupe by citation, sort by score, take top `limit`.
5. **Summaries for model:** `summarize_pks_for_model(pks_rows, 4)`, `summarize_evidence_for_model(evidence_rows, 4)` → short title/summary/excerpt for prompt.
6. **Optional drafter:** `build_drafter_context_pack()` uses a separate model call (task `context_pack`) to produce a “drafter_pack” injected into `retrieved_context`.
7. **Task prompt:** `build_task_prompt(user_text, connectivity, retrieved_context, system_hints)` in `hatori/prompts.py` — injects full `retrieved_context` as JSON (includes `pks_approved`, `local_evidence_top`, `drafter_pack`, `recent_feedback_summary`, optional `online_search_top`, `live_weather`).
8. **Generation:** Writer model (`reply_write` or `plan_write`) gets system prompt + task prompt; no formal “claim → source” contract in the template.

---

## 3) Components

| Component | Location | Role |
|-----------|----------|------|
| **PKS retrieval** | `hatori/cli.py` `retrieve_pks()` | Keyword scoring over pks_records (title+body); status filter Approved [± Pending]. |
| **Embeddings (keyword)** | `hatori/cli.py` `retrieve_embeddings()` | Keyword scoring over last 800 embedding rows (content); no vector used. |
| **Embeddings (semantic)** | `hatori/cli.py` `retrieve_embeddings_semantic()` | Query embedded via adapter; pgvector nearest-neighbour; term-overlap filter; score threshold 0.30. |
| **Merge / rank** | `hatori/cli.py` `merge_rank_results()` | Dedupe by citation; sort by score; take top N. |
| **Embedding adapter** | `hatori/embeddings.py` | `HashEmbeddingAdapter` (default, deterministic) or `SentenceTransformersAdapter`; `embed(texts)` → vectors. |
| **Chunking** | `ui/app.py` and `hatori/cli.py` `chunk_text()` | 900 chars, 120 overlap; used at ingest (API upload, CLI ingest) and for drafter. |
| **Online retrieval** | `ui/app.py` `online_search_snippets()` | SearXNG HTTP; used only in UI chat when `should_route_online_search()` and not OFFLINE. |
| **Task prompt** | `hatori/prompts.py` `build_task_prompt()` | Injects connectivity, user text, and full `retrieved_context` JSON; no structured “evidence block” or citation rules. |

---

## 4) Storage and indexing

- **PKS:** `pks_records` (module, title, body, status, provenance, etc.); no separate search index.
- **Artefacts:** `artefacts` (id, kind, uri, title, sha256, metadata).
- **Embeddings:** `embeddings` (id, artefact_id, chunk_id, content, embedding pgvector, metadata). Populated at ingest (CLI, API upload/ingest_path) via `chunk_text` + adapter `embed()`.

---

## 5) Gaps (high level, for D2)

- **No reranker:** Single merge by score; no cross-encoder or second-stage rerank.
- **No formal eval set:** No `tests/rag_eval/` or retrieval metrics in CI.
- **No “claim → source” contract in prompt:** Template asks to “cite provenance” but does not enforce structured grounding of each claim to a passage.
- **PKS in reply path is “recent N” not “query-relevant N”:** UI/API use `load_pks_context(limit=6)` (no query); only evidence is query-scored.
- **Keyword “embedding” path:** `retrieve_embeddings()` does not use vectors; name is misleading.

---

## 6) D2 — Retrieval quality gap list (prioritised)

| Priority | Gap | Impact |
|----------|-----|--------|
| P1 | **No retrieval eval set or metrics** | Cannot measure regression or compare changes; no CI gate for RAG quality. |
| P1 | **No formal claim → source grounding in prompt** | Model can answer without citing; no structured “each claim maps to one passage” contract. |
| P2 | **No reranker** | Single scoring merge; no second-stage rerank (e.g. cross-encoder or small model) to boost precision. |
| P2 | **PKS in reply is “recent 6” not query-scoped** | `load_pks_context(6)` ignores user query; only evidence is query-dependent. |
| P3 | **Keyword “embedding” path is misleading** | `retrieve_embeddings()` does not use vectors; naming/documentation can confuse. |
| P3 | **Chunk size/overlap fixed (900/120)** | No tuning or config for different doc types; may be suboptimal for long docs or dense snippets. |

---

## 7) References

- Delivery plan: [DELIVERY-PLAN-IDEA-BANK.md](../11-roadmap/DELIVERY-PLAN-IDEA-BANK.md) §3 #350.
- D3 decision: [RAG-decision-memo-D3.md](RAG-decision-memo-D3.md).
- D4 options: [RAG-architecture-options-D4.md](RAG-architecture-options-D4.md).
- D5 roadmap: [RAG-phased-roadmap-D5.md](RAG-phased-roadmap-D5.md).
- D6 follow-up issue drafts: [RAG-follow-up-issues-D6.md](../11-roadmap/RAG-follow-up-issues-D6.md).
- Interfaces (RAG): [interfaces.md](../10-api-contracts/interfaces.md) — `RAG.search_local`, `RAG.index_document`, `RAG.get_sources`.
