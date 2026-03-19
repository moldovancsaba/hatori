# Issue Register

Active planning and backlog: **GitHub Project #1** (see [backlog.md](backlog.md) for pointer). This file links to design/delivery docs and version context.

Current version context:
- `v0.8.5`
- Last updated: 2026-03-19

Design / delivery:
- **#280** (Integrator operator dashboard): LLD and delivery plan → [docs/11-roadmap/LLD-280-integrator-operator-dashboard.md](LLD-280-integrator-operator-dashboard.md)
- **#281** (Replay / anti-duplication): Replay semantics and single-event idempotency → [docs/10-api-contracts/replay-semantics.md](../10-api-contracts/replay-semantics.md)
- **#350** (RAG quality): D1–D6 docs; **Phase 1** [tests/rag_eval/README.md](../../tests/rag_eval/README.md); **Phase 2** grounding + `load_pks_context_for_reply`; **Phase 3** optional rerank [RAG-rerank-phase3.md](../06-evaluation/RAG-rerank-phase3.md) (`HATORI_RERANK_MODE`, golden 113–115)
- **IDEA BANK (#281, #350, #351, #352):** Breakdown, deliverables, clarification questions, and delivery order → [docs/11-roadmap/DELIVERY-PLAN-IDEA-BANK.md](DELIVERY-PLAN-IDEA-BANK.md)

Ops / audit:
- **Documentation vs code audit:** Inconsistencies, missing refs, implementation stage → [docs/04-ops/documentation-audit.md](../04-ops/documentation-audit.md)
- **Documentation, versioning, SSOT audit:** Version/CHANGELOG/SSOT vs implemented state, fix checklist → [docs/04-ops/documentation-versioning-ssot-audit.md](../04-ops/documentation-versioning-ssot-audit.md)
- **Audit remediation LLD:** Doc fixes + board issues → [docs/11-roadmap/LLD-documentation-audit-remediation.md](LLD-documentation-audit-remediation.md)
