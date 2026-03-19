# Evaluation

Behavioural and regression evaluation is done by the **golden test suite**:

- **Location:** `tests/golden/run_golden.py`
- **Run:** `make test` (includes golden suite after reset and self-tests) or `python tests/golden/run_golden.py`

The suite covers offline runtime behaviour, chat and upload UI flows, API ingest/respond/outcome, and operator dashboard. Formal `hatori.eval` wraps golden runs; see `docs/10-api-contracts/interfaces.md`.

**RAG quality (#350) — design docs:** [RAG-retrieval-audit-D1.md](RAG-retrieval-audit-D1.md) (audit + gaps), [RAG-decision-memo-D3.md](RAG-decision-memo-D3.md), [RAG-architecture-options-D4.md](RAG-architecture-options-D4.md), [RAG-phased-roadmap-D5.md](RAG-phased-roadmap-D5.md). Draft spin-off issues: [RAG-follow-up-issues-D6.md](../11-roadmap/RAG-follow-up-issues-D6.md).

**Phase 1 — retrieval eval in CI:** [tests/rag_eval/README.md](../../tests/rag_eval/README.md) (`make test` runs it after `dod_gate`, before golden). Programmatic entry: `hatori.eval.run_rag_eval_suite()`.
