# Documentation, versioning, and SSOT audit

**Date:** 2026-03-18 (post #281, #435, #350 D1–D3)  
**Scope:** Doc vs code, version consistency, SSOT (board/issues/HANDOVER) vs implemented state.

---

## 1) Executive summary

- **Versioning:** `VERSION` and CHANGELOG still at 0.8.0; multiple shipped items (#281, #435, #350 D1–D3, board script fix) are not in CHANGELOG. Recommendation: bump to 0.8.1 and add a CHANGELOG section, or add an "Unreleased" section.
- **Documentation:** Previous audit (documentation-audit.md) recommended actions were largely applied; two items are now **stale**: (1) interfaces.md was updated to "Implemented" but the audit doc still says "not yet implemented"; (2) golden test count is 105 (run) but docs say "100+" or "~100".
- **SSOT:** Several docs describe **board/card status** that has since changed (#281 Done, #350 Backlog + D1–D3 done, #435 Done). HANDOVER and LLD/DELIVERY-PLAN need light updates so "next step" and card state match reality.

---

## 2) Versioning inconsistencies

| Item | Current state | Issue |
|------|----------------|--------|
| **VERSION** | `0.8.0` | Correct as last tagged release. |
| **CHANGELOG.md** | Last section `[0.8.0]` 2026-03-18 | Does not list #281 (replay semantics, upload duplicate, test_98b), #435 (PKS/RAG/NET/EVAL modules), #350 (RAG audit D1–D2–D3), or board script fix (OWNER=@me). |
| **README.md** | Badge and text `v0.8.0` | Matches VERSION. If we bump to 0.8.1, README must follow. |
| **docs/00-overview/README.md** | "Current stable release: v0.8.0" | Same. |
| **docs/11-roadmap/issues.md** | "Current version context: v0.8.0" | Same. |

**Recommendation:** Add `## [0.8.1] - unreleased` (or with date) to CHANGELOG with entries for #281, #435, #350 D1–D3, board script; then bump VERSION to 0.8.1 and update README + overview + issues.md. Or keep 0.8.0 and add an "Unreleased" subsection under 0.8.0 listing these items until next release.

---

## 3) Documentation vs code (current)

| Doc | Assertion | Code reality | Action |
|-----|-----------|--------------|--------|
| **docs/04-ops/documentation-audit.md** §2.5, §5.8, §6 item 5 | interfaces.md describes "target" design; "not yet implemented as discrete modules". | **Implemented:** `hatori/pks.py`, `rag.py`, `net.py`, `eval.py`, `db.py`. interfaces.md already updated to "Implemented". | Update audit: mark §2.5/§5.8 as "remediated (implemented)"; §6 item 5 done. |
| **docs/04-ops/documentation-audit.md** §2.4 | "~100 test functions" | **105** tests in collect_tests (run_golden.py). | Optional: change to "105 golden tests" or leave "100+". |
| **docs/07-runbooks/runbook-local.md** | "100+ golden tests" | 105 tests run. | Optional: "105 golden tests" for precision. |
| **docs/11-roadmap/LLD-documentation-audit-remediation.md** | #435 "In Progress / Done", #435 "Backlog (SOONER)" in table. | #435 is **Done** on board. | Set #435 status to "Done" in LLD table. |
| **docs/11-roadmap/DELIVERY-PLAN-IDEA-BANK.md** | "Move #281 from IDEA BANK → Backlog (SOONER) when ready"; "Keep #350 in IDEA BANK until D1–D3 are done". | #281 is **Done**; #350 is **Backlog** and D1–D3 **done**. | Add a short "Status update" note: #281 Done; #350 Backlog, D1–D3 complete; next D4–D6. |
| **docs/11-roadmap/issues.md** | "Canonical issue-style planning is maintained in: docs/11-roadmap/backlog.md" | backlog.md says "Archived"; SSOT is GitHub project #1. | Change to: "Active backlog/SSOT: GitHub Project #1 (see backlog.md for pointer)." |
| **HANDOVER.md** | "#435 (Refactor, Backlog SOONER)"; "#281. Move to Done when ready". | #435 and #281 are **Done** on board. | Update to "#435 Done", "#281 Done" in those entries. |
| **HANDOVER.md** | "make test 104/104" (for #280). | Current suite is **105** (test_98b, test_43c added later). | Use "105/105" for recent entries or "make test PASS". |

---

## 4) SSOT consistency (board vs docs)

| Issue | Board state (intended) | Docs state | Fix |
|-------|-------------------------|------------|-----|
| #280 | Done | LLD and HANDOVER say Done. | OK. |
| #281 | Done | HANDOVER says "Move to Done when ready". | Update HANDOVER: #281 Done. |
| #339 | Done | Runbook and HANDOVER say Done. | OK. |
| #434 | Done | LLD says Done. | OK. |
| #435 | Done | LLD says "In Progress / Done"; HANDOVER says Backlog SOONER. | LLD: Done. HANDOVER: Done. |
| #436 | IDEA BANK | LLD says IDEA BANK. | OK. |
| #350 | Backlog (SOONER) | HANDOVER and issues.md link to D1–D3. DELIVERY-PLAN says "keep in IDEA BANK until D1–D3". | DELIVERY-PLAN: add status note. |

---

## 5) Recommended fixes (checklist)

1. **Versioning:** ~~Add CHANGELOG section for 0.8.1 (or Unreleased) with #281, #435, #350 D1–D3, board script; bump VERSION to 0.8.1; update README, overview, issues.md version line.~~ **Done:** VERSION=0.8.1; CHANGELOG [0.8.1]; README, overview, issues.md updated; dod_gate PASS.
2. **documentation-audit.md:** In §2.5 and §5.8 add "(Remediated: implemented as hatori.pks, rag, net, eval.)"; in §6 mark item 5 done; optionally §2.4 "100+" → "105".
3. **LLD-documentation-audit-remediation.md:** #435 status column → "Done".
4. **DELIVERY-PLAN-IDEA-BANK.md:** Add one-line status note at top of §2 and §3: #281 Done; #350 Backlog, D1–D3 done, next D4–D6.
5. **issues.md:** Replace "Canonical issue-style planning is maintained in: backlog.md" with "Active planning/backlog: GitHub Project #1. See backlog.md for pointer."
6. **HANDOVER.md:** In #281 and #435 entries, set card status to Done; optionally normalize test count to "105/105" where relevant.
7. **runbook-local.md:** Optional: "100+ golden tests" → "105 golden tests".

---

## 6) References

- Previous audit: [documentation-audit.md](documentation-audit.md)
- Versioning rule: [versioning-release.md](versioning-release.md)
- Board script: `tools/scripts/ssot_board_update.sh` (OWNER=@me)
