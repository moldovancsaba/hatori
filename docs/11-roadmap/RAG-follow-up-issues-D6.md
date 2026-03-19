# RAG quality — follow-up implementation issues (D6 for #350)

**Parent:** [mvp-factory-control#350](https://github.com/moldovancsaba/mvp-factory-control/issues/350).  
**Roadmap:** [RAG-phased-roadmap-D5.md](../06-evaluation/RAG-phased-roadmap-D5.md).

**Action:** Create the issues below in **mvp-factory-control** (or your SSOT tracker), link each **back to #350**, and add to **GitHub Project #1** with Product = {hatori}. Labels suggestion: `enhancement`, `hatori`, `rag` (if used).

---

## Issue 1 — RAG eval set and CI metrics

**Title:** `{hatori} RAG eval set and CI metrics (#350)`  

**Body (markdown):**

```markdown
Spin-off from #350 Phase 1 ([RAG-phased-roadmap-D5](https://github.com/moldovancsaba/hatori/blob/main/docs/06-evaluation/RAG-phased-roadmap-D5.md)).

## Goal
Add a small retrieval eval set and runnable metrics (recall@k, MRR, or "expected citation in top-k") so RAG/retrieval changes can be measured and guarded in CI.

## Scope
- Fixtures under `tests/rag_eval/` (or agreed path); document format in a README there.
- Runner integrated with `make test` or `make rag-eval` (document in runbook-local).
- Baseline numbers recorded in repo (doc or comment).

## Out of scope
- New reranker models; prompt-only changes (separate issue).

## Acceptance
- [ ] CI (or documented optional job) runs eval green on main.
- [ ] At least one failing scenario can be demonstrated by temporarily breaking retrieval (document how).
- [ ] Linked from #350; closes when Phase 1 exit criteria in D5 are met.

## Refs
- D1 audit: `docs/06-evaluation/RAG-retrieval-audit-D1.md`
- D3 memo: `docs/06-evaluation/RAG-decision-memo-D3.md`
```

---

## Issue 2 — Answer grounding contract (prompts + tests)

**Title:** `{hatori} Answer grounding contract in prompts and tests (#350)`  

**Body (markdown):**

```markdown
Spin-off from #350 Phase 2a ([RAG-phased-roadmap-D5](https://github.com/moldovancsaba/hatori/blob/main/docs/06-evaluation/RAG-phased-roadmap-D5.md)).

## Goal
Define and implement a prompt/contract so model answers tie factual claims to retrieved passages (citations / structured evidence expectations).

## Scope
- Update `hatori/prompts.py` (`build_task_prompt` and related) with clear citation rules aligned with `retrieved_context` shape.
- Tests: golden or rag_eval checks that are pragmatic (e.g. citation markers when evidence present), not flaky on live model variance where avoidable.

## Out of scope
- Reranker; PKS query-scoping (separate issue).

## Acceptance
- [ ] Contract described in a short doc or docstring + link from HANDOVER if needed.
- [ ] Automated test(s) pass on CI.
- [ ] Linked from #350.

## Refs
- D2 gaps (P1 claim→source): `docs/06-evaluation/RAG-retrieval-audit-D1.md` §6
```

---

## Issue 3 — PKS query-scoped context in UI/API reply path

**Title:** `{hatori} PKS query-scoped context for chat/API reply (#350)`  

**Body (markdown):**

```markdown
Spin-off from #350 Phase 2b ([RAG-phased-roadmap-D5](https://github.com/moldovancsaba/hatori/blob/main/docs/06-evaluation/RAG-phased-roadmap-D5.md)).

## Problem
Today `load_pks_context(6)` returns recent Approved PKS rows without query relevance; only local evidence is query-scored ([D1 audit](https://github.com/moldovancsaba/hatori/blob/main/docs/06-evaluation/RAG-retrieval-audit-D1.md)).

## Goal
Include query-relevant Approved PKS in the reply path (e.g. merge `retrieve_pks` with existing evidence limits), with sensible caps and ordering.

## Acceptance
- [ ] UI chat and API respond paths use agreed merge strategy; documented in audit doc or runbook.
- [ ] Golden test demonstrates query relevance when fixture supports it.
- [ ] Linked from #350.

## Refs
- `ui/app.py` — `load_pks_context`, `load_local_evidence_context`
- `hatori/cli.py` — `retrieve_pks`, `merge_rank_results`
```

---

## Issue 4 — Optional second-stage reranker (PO approval)

**Title:** `{hatori} Optional RAG reranker — design + implementation (#350, blocked: PO)`  

**Body (markdown):**

```markdown
Spin-off from #350 Phase 3 ([RAG-decision-memo-D3](https://github.com/moldovancsaba/hatori/blob/main/docs/06-evaluation/RAG-decision-memo-D3.md)): **do not start until PO approves** new model/API/latency.

## Preconditions
- Phase 1 eval and Phase 2 grounding (or explicit waiver) in place.
- Eval shows retrieval ranking (not only generation) as bottleneck.

## Goal
Pluggable rerank after `merge_rank_results`; default off; eval proves benefit when on.

## Acceptance
- [ ] Design note (ADR or doc in `docs/06-evaluation/`).
- [ ] Implementation behind config; runbook updated.
- [ ] Eval comparison rerank on vs off documented.

Blocked label or project column until PO approval.
```

---

## Checklist (for whoever creates the issues)

- [ ] Create issues 1–3 in **mvp-factory-control**; link to **#350** and paste URLs into a comment on #350.
- [ ] Add issues to **Project #1**; set **Product = {hatori}** if your board uses that field.
- [ ] Issue 4: create as **Backlog / Blocked** until PO approves rerank.
- [ ] Optionally close or narrow **#350** after D6 is tracked (“design complete; execution on spin-offs”).
