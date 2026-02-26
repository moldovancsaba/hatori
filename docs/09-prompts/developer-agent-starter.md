# Developer Agent Starter Prompt

Copy/paste this entire prompt into your developer agent.

---

You are implementing Hatori inside `/Users/moldovancsaba/Projects/reply-hatori`.
Baseline tag: `v0.4.0`

Non-negotiables:
- Canonical policy: `docs/01-charters/hatori-charter-v3.md`
- Prompt pack: `docs/09-prompts/`
- Offline-first. OSS only.
- Every memory state change must write `audit_events`.
- Before declaring done: update documentation, update versioning artefacts (`VERSION`, `CHANGELOG.md`), commit all changes, and push to `origin/main`.
- Provide short copy/paste terminal commands (no heredocs).
- Must not break: `make up`, `make reset`, `make test`, `make run-ui`, `./tools/scripts/planning_check.sh`

Current objectives (Sprint 04 baseline):
1) Chat UI + feedback loop:
   - `/chat`, `/chat/send`, `/chat/feedback`
   - feedback writes `learning_events` linked to assistant interaction IDs
2) Upload + retrieval UI:
   - `/upload` saves artefacts and ingests parseable files into `embeddings`
   - `/search` displays local results with provenance
3) Keep governance and auditability intact:
   - no auto-write to A–H without explicit action
   - PKS status changes write `audit_events`

Acceptance tests:
- `make reset && make test` passes.
- `planning_check.sh` passes.
- `/chat` send flow creates user+assistant `interaction_events` with `chat_id`.
- Chat feedback creates linked `learning_events` (`related_interaction_id` = assistant id).
- `/upload` creates artefact + embedding chunks for `.txt`/`.md`.
