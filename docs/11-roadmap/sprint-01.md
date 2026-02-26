# Sprint 01 — Next 10 Tasks

This sprint focuses on **governance + UX** so the system becomes usable daily.

## T1 — UI: approve/deprecate reason capture
- Add optional textarea “reason”
- Store reason in `audit_events.details`

## T2 — UI: PKS detail page
- `/pks/<uuid>` shows title/body/metadata + approve/deprecate buttons

## T3 — UI: export-to-disk snapshot
- Button writes `artefacts/exports/export-YYYYMMDD-HHMMSS.json`
- Register in `artefacts` table

## T4 — CLI: PKS governance completeness
- Ensure `approve/deprecate/contest` all create `audit_events`

## T5 — CLI: safer argument validation
- UUID validation everywhere
- refuse invalid module/status

## T6 — Runbook: end-to-end daily workflow
- 2–5 minute daily capture
- what goes to Pending, when to approve

## T7 — Ops: backup script
- DB dump + artefacts archive
- restore instructions

## T8 — Evaluation: golden test skeleton (10 tests)
- offline gating
- fabricated citations guard
- Memory Patch schema guard

## T9 — Ingestion skeleton
- `hatori ingest <path>` registers artefact + chunks to embeddings.content

## T10 — Retrieval skeleton
- `hatori search "<query>"` keyword search over embeddings.content + pks_records.body
