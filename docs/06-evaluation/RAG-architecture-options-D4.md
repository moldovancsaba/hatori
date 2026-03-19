# RAG quality — architecture options (D4 for #350)

**Issue:** [mvp-factory-control#350](https://github.com/moldovancsaba/mvp-factory-control/issues/350).  
**Decision (SSOT):** [RAG-decision-memo-D3.md](RAG-decision-memo-D3.md) — **eval-first → answer grounding → targeted rerank (if approved).**  
**Context:** [RAG-retrieval-audit-D1.md](RAG-retrieval-audit-D1.md) (gaps §6).

---

## 1) Purpose

Compare **2–3 coherent architecture paths** for improving retrieval and answer quality, so implementation can proceed in phases without re-litigating direction. Options below are **not** mutually exclusive in time: they map to **Phase 1 / 2 / 3** in [RAG-phased-roadmap-D5.md](RAG-phased-roadmap-D5.md).

---

## 2) Option A — Eval baseline only

**Scope:** Add a small **retrieval eval set** (fixtures + runner) and **metrics** (e.g. recall@k, MRR, or a simpler “expected citation in top‑k”) runnable locally and in CI. **No** change to merge logic, prompts, or models.

| Aspect | Notes |
|--------|--------|
| **Pros** | Lowest risk; establishes regression signal; no new runtime dependencies; aligns with “measure before tuning.” |
| **Cons** | Does not improve user-visible quality by itself; may need fixture maintenance as schema/chunking changes. |
| **Dependencies** | Deterministic retrieval path (existing `search_runtime` / ingest); optional `HATORI_MODEL=none` or fixed seed for stability. |
| **When to choose** | Hard gate on “no behaviour change until we can measure,” or parallel workstreams need a stable metric baseline first. |

---

## 3) Option B — Eval + grounding contract (recommended default)

**Scope:** Option A **plus** prompt/template and test changes so answers **tie claims to retrieved passages** (citations, structured evidence blocks, or explicit “source for X” instructions). Optionally **lightweight checks** in tests (e.g. presence of citation markers when evidence was injected).

| Aspect | Notes |
|--------|--------|
| **Pros** | High leverage without new models; improves interpretability and auditability; gains show up in eval if metrics include “grounded answer” or citation-in-top‑k alignment. |
| **Cons** | Prompt length and model compliance vary; strict “every claim → one passage” may need iteration. |
| **Dependencies** | Clear `retrieved_context` shape in `build_task_prompt`; eval set extended for “answer must cite” scenarios where feasible. |
| **When to choose** | Default path per D3; pairs with Phase 2 in D5. |

---

## 4) Option C — Eval + grounding + second-stage rerank

**Scope:** Option B **plus** a **rerank** step after current merge (e.g. cross-encoder, small local reranker, or approved external API). Rerank operates on **candidate list** from existing keyword + semantic + PKS merge.

| Aspect | Notes |
|--------|--------|
| **Pros** | Can improve precision@k and downstream answer quality when merge scores are noisy. |
| **Cons** | New dependency (model binary, memory, latency); harder to run in minimal CI unless mocked; needs PO approval per D3. |
| **Dependencies** | Stable eval from Phase 1; grounding contract from Phase 2 so improvements are attributable; infra for optional model load. |
| **When to choose** | Phase 3 only, after metrics show retrieval (not just generation) is the bottleneck and PO approves. |

---

## 5) Comparison matrix

| Criterion | A — Eval only | B — Eval + grounding | C — Full stack |
|-----------|---------------|----------------------|----------------|
| **Implementation effort** | Low | Medium | High |
| **New model / heavy deps** | No | No | Yes (reranker) |
| **User-visible quality** | Indirect | Direct (citations) | Direct + ranking |
| **Regression signal** | Strong | Strong (if eval extended) | Strong |
| **Aligns with D3** | Phase 1 | Phases 1–2 | Phases 1–3 |

**Recommendation:** Proceed **A → B → (conditional) C**, as in D3 and D5. Do not start C before Phase 1 eval exists.

---

## 6) Related design choices (cross-cutting)

| Topic | Options | Note |
|-------|---------|------|
| **PKS in reply path** | Keep “recent 6” vs **query-scoped PKS** (reuse `retrieve_pks` or merge with evidence) | D3 treats query-scoped PKS as pipeline tuning in Phase 2; see follow-up issue in [RAG-follow-up-issues-D6.md](../11-roadmap/RAG-follow-up-issues-D6.md). |
| **Eval data** | Public `tests/rag_eval/` vs internal-only | PO default in D3: public fixtures unless policy forbids. |
| **Keyword path naming** | Rename/clarify `retrieve_embeddings` (non-vector) | P3 hygiene; can be a small refactor issue. |

---

## 7) References

- Phased roadmap: [RAG-phased-roadmap-D5.md](RAG-phased-roadmap-D5.md)
- Draft follow-up issues: [RAG-follow-up-issues-D6.md](../11-roadmap/RAG-follow-up-issues-D6.md)
- Delivery plan: [DELIVERY-PLAN-IDEA-BANK.md](../11-roadmap/DELIVERY-PLAN-IDEA-BANK.md) §3
