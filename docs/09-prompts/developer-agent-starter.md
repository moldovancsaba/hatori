# Developer Agent Starter Prompt

Copy/paste this entire prompt into your developer agent.

---

You are implementing Hatori inside `/Users/moldovancsaba/Projects/reply-hatori`.

Non-negotiables:
- Canonical policy: `docs/01-charters/hatori-charter-v3.md`
- Prompt pack: `docs/09-prompts/`
- Offline-first. OSS only.
- Every memory state change must write `audit_events`.
- Provide short copy/paste terminal commands (no heredocs).
- Must not break: `make up`, `make reset`, `make test`, `make run-ui`, `./tools/scripts/planning_check.sh`

First objectives (Sprint 01):
1) UI: add “reason” input for approve/deprecate and store it in `audit_events.details`.
2) UI: add PKS detail page `/pks/<uuid>` showing record body + approve/deprecate.
3) UI: add export-to-disk button that writes JSON snapshot under `artefacts/exports/` and registers the artefact in the `artefacts` table.
4) CLI: ensure `hatori pks approve/deprecate/contest` also writes `audit_events`.

Acceptance tests:
- After approve/deprecate in UI, `audit_events` row exists with `actor=ui`, `action=approve|deprecate`, `target_id=<uuid>`, `details` contains reason (if provided).
- `/pks/<uuid>` renders and works.
- Export creates a file and an `artefacts` row.
- `make reset && make test` passes.
- `planning_check.sh` passes.
