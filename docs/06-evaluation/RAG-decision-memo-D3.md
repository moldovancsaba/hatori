# RAG quality — decision memo (D3 for #350)

**Issue:** [mvp-factory-control#350](https://github.com/moldovancsaba/mvp-factory-control/issues/350).  
**Context:** [RAG-retrieval-audit-D1.md](RAG-retrieval-audit-D1.md) (entry points, gaps).

---

## 1) Chosen path

**Eval-first → answer grounding → targeted rerank (if approved).**

| Order | Initiative | Description |
|-------|------------|-------------|
| **1** | **Eval set + metrics** | Add a small retrieval eval set (queries + expected/relevant passages or citations) and metrics (e.g. recall@k, MRR) runnable in CI. No product behaviour change; enables measuring impact of later changes. |
| **2** | **Answer grounding contract** | Define and implement a prompt/contract so that model output is expected to tie claims to specific passages (e.g. “cite [citation] for X”). Enforce or encourage via template and instructions; optional lightweight checks (e.g. citation presence) in tests. |
| **3** | **Targeted rerank (conditional)** | If metrics and PO approval allow: add a second-stage reranker (e.g. small local model or configurable external) on top of current retrieval. Scope and backend to be decided when Phase 2 is done; default assumption until then: **prompt/config only**, no new model dependency. |

---

## 2) Rationale

- **Eval first:** Without metrics we cannot compare “before vs after” or guard against regression. A small public eval set in repo (e.g. `tests/rag_eval/`) supports CI and local iteration; internal-only is acceptable if policy requires it.
- **Grounding before rerank:** Improving “does the answer cite the right things?” has high leverage and can be done with prompt/template changes. Rerank improves retrieval order but does not by itself enforce citation; doing grounding first makes rerank gains measurable (eval metrics on grounded answers).
- **Rerank conditional:** Reranker adds dependency and complexity; recommendation is to add only after eval and grounding are in place and PO explicitly approves (local or external model). Until then, improvements are prompt/config and retrieval pipeline tuning (e.g. score thresholds, PKS query-scoping).

---

## 3) Out of scope (for this decision)

- Changing the default embedding model (hash vs sentence-transformers remains a config choice).
- Full cross-encoder or heavy reranker in the first implementation phase.
- Query expansion or multi-query retrieval until eval shows a clear gap.
- Replacing “recent PKS” with query-scoped PKS is in scope (counts as retrieval pipeline tuning); details in Phase 2.

---

## 4) Assumptions / open points

- **Eval set location:** Recommendation is **public fixtures** in repo (e.g. `tests/rag_eval/`) unless policy requires internal-only. PO can override.
- **Reranker:** Until PO approves, all improvements are **prompt/config and retrieval logic only**; no new reranker model or external API. If/when approved, prefer local small model for local-first alignment.
- **Grounding strictness:** Phase 2 can start with “recommend citing” and optional tests that check for citation presence; stricter “every claim → one passage” can follow if needed.

---

## 5) Next steps (D4–D6)

- **D4:** Short doc with 2–3 architecture options (e.g. eval-only vs eval+grounding vs eval+grounding+rerank), tradeoffs, dependencies.
- **D5:** Phased roadmap (Phase 1: eval set + metrics; Phase 2: grounding contract + optional PKS query-scoping; Phase 3: rerank if approved).
- **D6:** Create follow-up implementation issues (e.g. “RAG eval set and metrics”, “Answer grounding contract”) and link from #350.

---

## 6) References

- Audit and gaps: [RAG-retrieval-audit-D1.md](RAG-retrieval-audit-D1.md)
- Delivery plan: [DELIVERY-PLAN-IDEA-BANK.md](../11-roadmap/DELIVERY-PLAN-IDEA-BANK.md) §3
