# RAG quality — phased roadmap (D5 for #350)

**Issue:** [mvp-factory-control#350](https://github.com/moldovancsaba/mvp-factory-control/issues/350).  
**Decision:** [RAG-decision-memo-D3.md](RAG-decision-memo-D3.md).  
**Options context:** [RAG-architecture-options-D4.md](RAG-architecture-options-D4.md).

---

## 1) Principles

1. **No reranker dependency** until Phase 1 metrics exist and Phase 2 grounding is in flight or done.  
2. **Every phase** leaves the repo in a shippable state (tests green; docs updated).  
3. **PO gates:** eval fixture policy (public vs internal); reranker approval before Phase 3.

---

## 2) Phase 1 — Eval set + metrics

**Goal:** Measure retrieval (and optionally simple “citation in context”) before changing ranking or prompts.

| Work item | Acceptance hint |
|-----------|-----------------|
| **Fixtures** | Small curated set under e.g. `tests/rag_eval/` (or agreed path): ingested snippets or stable artefact IDs + queries + expected chunk_ids or citation keys. **Done:** `tests/rag_eval/fixtures/`, `cases.json`, reuse golden `semantic_garage.txt` / `offline_playbook.txt`. |
| **Runner** | Script or pytest module that: ingests/fixtures DB state (or uses golden-style setup), runs `search_runtime` (or narrower API), asserts metrics. **Done:** `tests/rag_eval/run_rag_eval.py` (CLI `search`); `hatori.eval.run_rag_eval_suite()`. |
| **Metrics** | At least one of: recall@k, MRR, or “expected citation appears in top‑k results”; document definitions in README in eval folder. **Done:** per-case recall@k + MRR; mean summary in runner output. |
| **CI** | `make test` or dedicated target (e.g. `make rag-eval`) documented in runbook; fast enough for default CI or optional job clearly documented. **Done:** `make test` runs RAG eval after `dod_gate`, before golden; `make rag-eval` for ad hoc. |
| **Baseline** | Record baseline numbers in doc or comment in repo so regressions are visible. |

**Exit criteria:** CI (or documented job) runs eval; failing case reproduces a known bad retrieval; no required change to production prompt yet. **Met** (2026-03-18): `make test` includes RAG eval on clean post-seed DB.

**Primary follow-up issue:** D6 — “RAG eval set and CI metrics” (implementation landed; issue can track extensions / more cases).

---

## 3) Phase 2 — Answer grounding + retrieval tuning

**Goal:** Improve **answer–evidence alignment** and optionally **query-scoped PKS** without new rerank models.

### 2a — Grounding contract

| Work item | Acceptance hint |
|-----------|-----------------|
| **Prompt / template** | `build_task_prompt` (or adjacent) instructs: cite sources for factual claims; use stable citation labels matching `retrieved_context`. **Done:** `docs/09-prompts/task-prompt-template.md` Answer grounding block; `pks_approved` / `local_evidence_top` entries include `citation` via `summarize_pks_for_model` / `summarize_evidence_for_model` (`ui/app.py`). |
| **Tests** | Golden or rag_eval cases where model output is stubbed or constrained check for citation presence when evidence rows exist (pragmatic, not brittle). **Done:** `test_110_*`, `test_111_*` (citations in summaries + grounding text in task prompt). Optional later: live-model citation checks. |
| **Docs** | Short subsection in API/UI doc or prompts doc describing grounding expectations. **Done:** task template + this roadmap. |

### 2b — PKS query-scoping (recommended in D3 as pipeline tuning)

| Work item | Acceptance hint |
|-----------|-----------------|
| **Behaviour** | UI/API reply path uses query-relevant PKS (e.g. merge `retrieve_pks` top‑m with existing evidence) instead of or in addition to “recent 6 only.” **Done:** `load_pks_context_for_reply` in `ui/app.py`; chat + API respond use it. |
| **Tests** | Golden test: query that matches an older Approved PKS row ranks it above irrelevant recent rows (fixture-dependent). **Done:** `test_112_reply_pks_context_prefers_query_relevant`. |
| **Rollback** | Feature flag or env toggle optional if risk warrants. |

**Exit criteria:** Grounding instructions merged; at least one automated test guards behaviour; PKS query-scoping implemented or explicitly deferred with issue link. **Met** (2026-03-19) for template + summaries + reply PKS loader + golden 110–112.

**Primary follow-up issues:** D6 — “Answer grounding contract”; “PKS query-scoped context in reply path.”

---

## 4) Phase 3 — Targeted rerank (conditional)

**Preconditions:** Phase 1 baseline stable; Phase 2 done or scoped; **PO approval** for new model/API/latency budget.

| Work item | Acceptance hint |
|-----------|-----------------|
| **Design note** | Where rerank sits (after `merge_rank_results`, input size cap, timeout). **Done:** [RAG-rerank-phase3.md](RAG-rerank-phase3.md). |
| **Implementation** | Pluggable adapter (e.g. `None` vs local model); default off. **Done:** `rerank_merged_results()` + `HATORI_RERANK_MODE` (`off` default, `lexical` = overlap + score, no new model deps). |
| **Eval** | Phase 1 metrics show improvement on rerank branch vs off (A/B in runner). **Partial:** golden 113–115; manual A/B on `tests/rag_eval` optional. |
| **Ops** | Runbook: env vars, memory, fallbacks. **Done:** runbook-local + design doc. |

**Exit criteria:** Rerank optional path merged; eval proves non-regression when disabled; documented PO sign-off in issue or ADR. **Met** for lexical optional path + default off (2026-03-19). Heavy reranker still PO-gated.

**Primary follow-up issue:** D6 — “Optional reranker (PO approval).” Cross-encoder mode can extend `rerank_merged_results` later.

---

## 5) Suggested sequencing (timeline-agnostic)

```text
Phase 1 (eval) ──► Phase 2a (grounding) ──┬──► Phase 2b (PKS scope) ──► Phase 3 (rerank, if approved)
                                            └──► can parallel 2a/2b with two owners if desired
```

---

## 6) References

- Gaps: [RAG-retrieval-audit-D1.md](RAG-retrieval-audit-D1.md) §6  
- Draft GitHub issues: [RAG-follow-up-issues-D6.md](../11-roadmap/RAG-follow-up-issues-D6.md)  
- Formal RAG interface: [interfaces.md](../10-api-contracts/interfaces.md)
