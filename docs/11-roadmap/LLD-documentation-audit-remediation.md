# LLD: Documentation audit remediation

**Context:** [docs/04-ops/documentation-audit.md](../04-ops/documentation-audit.md) (2026-03-18) identified doc/code inconsistencies and missing references. This LLD records the remediation and breaks remaining work into project issues.

---

## 1) Scope

- **Completed (doc fixes):** Align docs with code; add missing placeholders; clarify runbooks and contracts.
- **Optional follow-on (tracked as separate issues):** Circuit breaker for model backends; formal PKS/RAG/NET/EVAL modules per interfaces.md.

---

## 2) Completed deliverables

| # | Action | Doc/change |
|---|--------|------------|
| D1 | Overview: Model Gateway → Model routing | `docs/00-overview/README.md` — section rewritten to describe `hatori/model.py`, task-based routing, no circuit breaker. Duplicate Planning/Release/API/Prompt block removed. |
| D2 | Overview: Where things live | PKS ref → `docs/03-data/` (overview), `pks/migrations/` (SQL). Evaluation → `docs/06-evaluation/` (overview), golden suite in `tests/golden/run_golden.py`. Audit link added. |
| D3 | API contract: health response | `docs/10-api-contracts/hatori-api-v1.md` — added `ok`, `statusMessage` to §8.1; note "additional fields may be present". |
| D4 | Runbook UI: port and target | `docs/07-runbooks/runbook-ui.md` — clarified `make run-ui` = dev-only (8088); full stack = `make run` / run-ui-hatori (23571). |
| D5 | Runbook local: golden count | `docs/07-runbooks/runbook-local.md` — "50 golden tests" → "100+ golden tests". |
| D6 | Interfaces: target vs current | `docs/10-api-contracts/interfaces.md` — title "Target Implementation Contracts"; status note that behaviour is implemented via direct DB/CLI/UI/API, not yet as discrete modules. |
| D7 | Placeholder READMEs | `docs/03-data/README.md`, `docs/06-evaluation/README.md` — point to pks/migrations and tests/golden/run_golden.py. |

---

## 3) Project board issues (mvp-factory-control)

| Issue | Title | Type | Status | Description |
|-------|--------|------|--------|-------------|
| **#434** | Documentation audit remediation — align docs with code | Docs | Done | Track doc fixes D1–D7. Remediation applied in hatori; card on project #1. |
| **#435** | Refactor: PKS/RAG/NET/EVAL as formal modules (interfaces.md) | Refactor | In Progress / Done | Implemented: `hatori/db.py`, `hatori/pks.py`, `hatori/rag.py`, `hatori/net.py`, `hatori/eval.py`. Golden test `test_43c_formal_modules_interface` exercises PKS.query, NET.status, RAG.search_local, RAG.get_sources. See audit §2.5, §5.8. |
| **#436** | Optional: Circuit breaker for model backends | Plan | IDEA BANK | Process-local breaker for failing backends; expose state in /v1/health. See audit §2.1, §5.8. |

---

## 4) Acceptance (remediation)

- [x] Overview describes model routing in `hatori/model.py` only; no model_gateway.py or circuit breaker claim.
- [x] All audit §6 action items 1–6 addressed (overview, API contract, runbook-ui, runbook-local, interfaces, placeholders).
- [x] Doc-to-code map in audit remains valid; no new inconsistencies introduced.
- [x] Issues #434, #435, #436 created on mvp-factory-control and added to project #1 (Product: {hatori}; #434 Done/Docs, #435 Backlog/Refactor, #436 IDEA BANK/Plan).

---

## 5) References

- Audit: [docs/04-ops/documentation-audit.md](../04-ops/documentation-audit.md)
- API contract: [docs/10-api-contracts/hatori-api-v1.md](../10-api-contracts/hatori-api-v1.md)
- Interfaces (target): [docs/10-api-contracts/interfaces.md](../10-api-contracts/interfaces.md)
- Roadmap index: [docs/11-roadmap/issues.md](issues.md)
