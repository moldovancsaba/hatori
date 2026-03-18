# Brain dump — operational rules and gotchas

Single source for operational gotchas, standing rules, and decisions. Use this document to **refer** from runbooks, agent prompts, and code comments (e.g. `see docs/BRAIN_DUMP.md` or `docs/BRAIN_DUMP.md#chat-no-hardcoded-answers`).

**How to use**
- **Rules** have stable anchors: link with `#rule-<slug>`.
- When changing behaviour or discovering a gotcha: add or update an entry here, then update `docs/HANDOVER.md` and any runbook that depends on it.
- Continuation log and 70-protocol handover: [docs/07-runbooks/braindump-next-agent.md](07-runbooks/braindump-next-agent.md).

---

## Table of contents

1. [Rules (referenceable)](#rules-referenceable)
2. [Gotchas and decisions](#gotchas-and-decisions)
3. [Changelog](#changelog)

---

## Rules (referenceable)

These are standing rules. Do not violate them without explicit PO approval.

### <a id="rule-chat-no-hardcoded-answers"></a>Chat: no hardcoded answers

**Slug:** `chat-no-hardcoded-answers`

- Hardcoded chat answers are **prohibited**.
- Planning failures (model error, empty or malformed JSON) must show only an **explicit error message and retry guidance** (e.g. start Ollama, resend request).
- Never return a fake plan template or any other pre-written “answer” as if it were the model’s reply.

*Reference:* HANDOVER 2026-03-16; braindump-next-agent.md Latest learnings.

---

### <a id="rule-leakage-blocking"></a>Chat: leakage blocking

**Slug:** `leakage-blocking`

- Treat internal scaffold leakage as a hard failure; fall back deterministically.
- Do not surface UUID, `emb:`, `artefact_id`, `User request:` echo, or other internal scaffolding to the user.

---

### <a id="rule-planning-intent-boundaries"></a>Planning intent: word boundaries

**Slug:** `planning-intent-boundaries`

- Naive substring planning detection (e.g. `"ma"` inside words like `email`) causes misrouting into planning logic.
- Intent gates for daily planning should use **regex word boundaries** (or equivalent) so only real “ma”/“nap”/planning phrases trigger the planning path.

---

## Gotchas and decisions

- **Reply integration:** Can still receive unusable text even when model runtime is technically available; treat scaffold leakage as hard failure and fall back deterministically.
- **Menubar/service health:** May show repeated “foreign process owns port” when UI/API were started manually; launchd service mode intentionally refuses takeover for safety.
- **API and UI:** Share logic through `ui.app` helpers by design; API and UI both use `ui.app` for shared behaviour.

---

## Changelog

| Date       | Change |
|-----------|--------|
| 2026-03-16 | Initial BRAIN_DUMP.md; added rule `chat-no-hardcoded-answers`, `leakage-blocking`, `planning-intent-boundaries`; migrated gotchas from braindump-next-agent. |
