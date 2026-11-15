# Project board review and manual movement / Scrum journal

Reviewed: 2026-11-15 UTC. Repository: moldovancsaba/hatori.

Canonical board: [Project 6](https://github.com/users/moldovancsaba/projects/6). **The owner's board is read-only. Never create, move, remove or reorder cards or edit project fields.** This document records evidence and conditional owner-action proposals, never executed moves.

## Verified scope and blockers

- Read the complete repository collection: 21 entries, including 11 issues and 10 pull requests. Four issues are open.
- Read all 10 board items and field definitions. Six cards are Done; #12, #15 and #17 are IDEABANK (SOMEDAY); #16 is Backlog (SOONER).
- Board and linked issue states agree. All four open issues are on this board. No exact title/body duplicate was found.
- Board/issue read access succeeded; no board access blocker was observed here. No board writes were attempted.
- Inspected [README](../README.md), [model adapters](../hatori/model.py), [retrieval runtime](../hatori/cli.py), [RAG facade](../hatori/rag.py), [PKS helpers](../hatori/pks.py), [API](../api/app.py), [Makefile](../Makefile) and the planning check.
- Product runtime acceptance and database/model behavior were not retested. make test starts with make reset; no isolated disposable test database was established, so that reset-based suite was not run for a documentation-only review. No user memory, database, model, service or provider setting changed.
- The requested planning check was attempted; its actual result is recorded below. No successful full product gate is claimed.

## Current work and modernization assessment

| Issue | Evidence-based disposition / next acceptance |
| --- | --- |
| [#12](https://github.com/moldovancsaba/hatori/issues/12) | Optional reliability work remains valid: adapter selection and health probing are not a circuit breaker. Define failure threshold, cooldown/half-open behavior, per-backend state and health DTO evidence before implementation. |
| [#15](https://github.com/moldovancsaba/hatori/issues/15) | Retain identity and privacy requirements. Stable surrogate contact identity and an explicitly authorized reversible mapping have different duties; model replacement is not an identity-resolution or privacy control. |
| [#16](https://github.com/moldovancsaba/hatori/issues/16) | Rebaseline on existing retrieval: hatori/cli.py search_runtime already merges PKS, keyword and semantic hits and calls rerank_merged_results. Benchmark present behavior on a frozen corpus before adding another retriever or reranker. Keep local-first, source grounding and measured quality as acceptance. |
| [#17](https://github.com/moldovancsaba/hatori/issues/17) | Retain PII processing at storage, indexing, retrieval and output boundaries. hatori/pks.py redact deprecates a PKS record; it does not prove free-text PII detection or channel-sensitive masking. Use bounded detection/policy evaluation and explicit authorization; no production ingestion or data inspection in this review. |

Existing local PostgreSQL/pgvector, adapter and RAG boundaries remain the baseline. Hybrid retrieval and reranking are already present in source, so selecting a newer framework does not itself justify replacing them. No external service or dependency was selected or installed. For the central portfolio's older Hatori tickets, compare this product board and source rather than reviving an old implementation premise. [Central review](https://github.com/moldovancsaba/mvp-factory-control/issues/942).

## Per-card movement register

| Issue / card | Issue state | Verified current column | Proposed destination | Condition / owner decision | Executed / read back |
| --- | --- | --- | --- | --- | --- |
| [#12](https://github.com/moldovancsaba/hatori/issues/12) Optional: Circuit breaker for model backends | open | IDEABANK (SOMEDAY) | Remain | Optional reliability work remains valid: adapter selection and health probing are not a circuit breaker. Define failure threshold, cooldown/half-open behavior, per-backend state and health DTO evidence before implementation. | No / no |
| [#13](https://github.com/moldovancsaba/hatori/issues/13) {hatori}: Idea Bank — Bulk ingest anti-duplication improvements | closed | Done | Remain | Preserve historical completion evidence; no new acceptance claim. | No / no |
| [#14](https://github.com/moldovancsaba/hatori/issues/14) {hatori}: Idea Bank — Integrator operator dashboard for approval/edit ratios | closed | Done | Remain | Preserve historical completion evidence; no new acceptance claim. | No / no |
| [#15](https://github.com/moldovancsaba/hatori/issues/15) {hatori}: Idea Bank - PII-safe contact identity model for communication tools | open | IDEABANK (SOMEDAY) | Remain | Retain identity and privacy requirements. Stable surrogate contact identity and an explicitly authorized reversible mapping have different duties; model replacement is not an identity-resolution or privacy control. | No / no |
| [#16](https://github.com/moldovancsaba/hatori/issues/16) {hatori}: Idea Bank - RAG quality improvement options and roadmap | open | Backlog (SOONER) | Remain | Rebaseline on existing retrieval: hatori/cli.py search_runtime already merges PKS, keyword and semantic hits and calls rerank_merged_results. Benchmark present behavior on a frozen corpus before adding another retriever or reranker. Keep local-first, source grounding and measured quality as acceptance. | No / no |
| [#17](https://github.com/moldovancsaba/hatori/issues/17) {hatori}: Idea Bank - PII control pipeline before storage, indexing, and output | open | IDEABANK (SOMEDAY) | Remain | Retain PII processing at storage, indexing, retrieval and output boundaries. hatori/pks.py redact deprecates a PKS record; it does not prove free-text PII detection or channel-sensitive masking. Use bounded detection/policy evaluation and explicit authorization; no production ingestion or data inspection in this review. | No / no |
| [#18](https://github.com/moldovancsaba/hatori/issues/18) {hatori}: Fix MLX runtime down in health/menu status | closed | Done | Remain | Preserve historical completion evidence; no new acceptance claim. | No / no |
| [#19](https://github.com/moldovancsaba/hatori/issues/19) {hatori}: startup hardening + MLX reliability recovery | closed | Done | Remain | Preserve historical completion evidence; no new acceptance claim. | No / no |
| [#20](https://github.com/moldovancsaba/hatori/issues/20) Documentation audit remediation — align docs with code | closed | Done | Remain | Preserve historical completion evidence; no new acceptance claim. | No / no |
| [#21](https://github.com/moldovancsaba/hatori/issues/21) Refactor: PKS/RAG/NET/EVAL as formal modules (interfaces.md) | closed | Done | Remain | Preserve historical completion evidence; no new acceptance claim. | No / no |

## Append-only Scrum / manual movement journal

| Date / Scrum reference | Issue / card | Observed Status | Proposed Status | Evidence / rationale | Dependency / blocker | Owner decision | Manual execution / person | Verified new Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-15 review | All 10 cards | Current values above | Remain | No linked issue-state mismatch found | Open requirements retained | No move proposed | Not executed | Snapshot only | No runtime acceptance repeated |
| YYYY-MM-DD / meeting link | Issue URL | Exact observed value | Exact proposed value | Evidence link | Specific condition | Pending | Not executed | Not verified | — |

Read issue and board before every new proposal, preserve earlier rows when a decision changes, and record execution only after the owner acts and the result is read back. Rollback is a documentation revert; no product or board rollback is needed.

## Planning check result

The check stopped at line 4 because it changes directory to `/Users/moldovancsaba/Projects/hatori`, which does not exist on this host. The full planning check did not run to completion. This machine-specific script path is a verification limitation, not a board-access failure. The script and operator machine were not changed for this documentation task.
