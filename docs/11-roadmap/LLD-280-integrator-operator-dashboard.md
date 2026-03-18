# LLD: #280 Integrator operator dashboard (approval/edit ratios + model-route quality)

**SSOT:** [mvp-factory-control#280](https://github.com/moldovancsaba/mvp-factory-control/issues/280)  
**Objective:** Add an operator dashboard to track sent_as_is vs edited_then_sent and model-route quality trends across integrators.  
**Constraint:** Existing API contract unchanged.

---

## 1. Recommendation (why #280 first)

- **Immediate value:** Builds on the learning/outcome loop we just reinforced (accept vs edit → learning_events + delivery_events). Dashboard makes that loop visible to the PO/ops.
- **Bounded scope:** Metrics + one read-only view; no new API surface required (optional read-only endpoint or UI-only queries).
- **Data exists:** `delivery_events` (status, platform, occurred_at) and `learning_events` (kind, related_interaction_id) already support the metrics.
- **Low risk:** Additive UI and optional internal endpoint; no schema change to existing tables.

Other IDEA BANK cards:
- **#281** (bulk ingest anti-duplication): Important for scale but touches idempotency and replay semantics; better after dashboard.
- **#350** (RAG quality): Discovery/roadmap card; outputs follow-up cards, not a single deliverable.
- **#351 / #352** (PII): Broad touch, schema impact, dependency chain; recommend after #280.

---

## 2. Core metrics and data sources

### 2.1 Primary metrics (outcome ratios)

| Metric | Definition | Data source |
|--------|------------|-------------|
| **sent_as_is count** | Number of outcomes with `status = 'sent_as_is'` | `delivery_events` |
| **edited_then_sent count** | Number of outcomes with `status = 'edited_then_sent'` | `delivery_events` |
| **not_sent count** | Number of outcomes with `status = 'not_sent'` | `delivery_events` |
| **approval ratio** | sent_as_is / (sent_as_is + edited_then_sent) over a window | Derived |
| **edit ratio** | edited_then_sent / (sent_as_is + edited_then_sent) over a window | Derived |

Optional: **by platform** (group by `delivery_events.platform`) so integrators (e.g. `{reply}`) can be compared.

### 2.2 Secondary metrics (model-route quality)

| Metric | Definition | Data source |
|--------|------------|-------------|
| **PositiveFeedback count** | learning_events with kind = 'PositiveFeedback' | `learning_events` |
| **NegativeFeedback count** | learning_events with kind = 'NegativeFeedback' | `learning_events` |
| **Outcome-linked feedback** | Learning events where details->>'external_outcome_id' is set | `learning_events` |

Trends = same metrics over time windows (e.g. last 7 days, last 30 days). No new tables; all from existing `delivery_events` and `learning_events`.

### 2.3 Data source details

- **delivery_events:** `id`, `external_outcome_id`, `assistant_interaction_id`, `status`, `platform`, `occurred_at`, (optional: `conversation_id`, `recipient_id` for grouping).
- **learning_events:** `id`, `kind`, `confidence`, `details` (jsonb: `external_outcome_id`, `status`, etc.), `occurred_at`, `related_interaction_id`.

No PII in dashboard: use counts and ratios only; no display of `original_text` / `final_sent_text` in the operator view (those stay in existing detail/audit flows).

---

## 3. Architecture options

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. UI-only (server-rendered)** | New route (e.g. `/outcomes` or `/operator`) that runs SQL in `ui/app.py` and renders HTML table/cards. | No API change; minimal code; reuses layout. | No programmatic access; harder to add charts later. |
| **B. UI + optional read-only API** | Same as A, plus optional `GET /v1/operator/metrics` (or under `/internal`) returning JSON for future use. | API for scripts/CI or future dashboard; still no contract change to existing endpoints. | Slightly more surface to maintain. |
| **C. Separate analytics DB** | ETL from delivery_events/learning_events into a separate store; dashboard reads from that. | Scales to very high volume. | Overkill for current scale; new infra. |

**Recommendation:** **Option A** for first delivery (fastest, no API change). Add **Option B** only if PO requests programmatic access or a second consumer.

---

## 4. Low-level design (Option A)

### 4.1 New UI route

- **Path:** `/outcomes` (or `/operator`).
- **Method:** GET.
- **Auth:** Same as other UI routes (no extra auth for now; operator dashboard is local-only).
- **Behavior:**
  1. Query aggregates from `delivery_events` and `learning_events` (see 4.2).
  2. Render a single page with:
     - Summary cards: total sent_as_is, edited_then_sent, not_sent (e.g. last 30 days).
     - Approval ratio and edit ratio (last 7 d, last 30 d).
     - Optional: breakdown by `platform` (table or list).
     - Optional: PositiveFeedback / NegativeFeedback counts (last 7 d, 30 d) for trend.
  3. Use existing `layout()` and card styling for consistency with `/learning` and `/interactions`.

### 4.2 Queries (example SQL)

**Delivery counts (last 30 days):**
```sql
SELECT status, count(*) AS cnt
FROM delivery_events
WHERE occurred_at >= now() - interval '30 days'
GROUP BY status;
```

**Approval / edit ratio (last 7 days):**
```sql
SELECT
  count(*) FILTER (WHERE status = 'sent_as_is') AS sent_as_is,
  count(*) FILTER (WHERE status = 'edited_then_sent') AS edited_then_sent,
  count(*) FILTER (WHERE status = 'not_sent') AS not_sent
FROM delivery_events
WHERE occurred_at >= now() - interval '7 days';
```
Ratio = sent_as_is / (sent_as_is + edited_then_sent) when denominator > 0.

**By platform (optional):**
```sql
SELECT platform, status, count(*) AS cnt
FROM delivery_events
WHERE occurred_at >= now() - interval '30 days'
GROUP BY platform, status
ORDER BY platform, status;
```

**Learning feedback counts (optional):**
```sql
SELECT kind, count(*) AS cnt
FROM learning_events
WHERE occurred_at >= now() - interval '30 days'
  AND kind IN ('PositiveFeedback', 'NegativeFeedback')
GROUP BY kind;
```

### 4.3 Menu / navigation

- Add a link to the new route in the existing UI nav (e.g. in `layout()` or the same block as "Learning", "Interactions"): e.g. "Outcomes" or "Operator".
- Optional: add to HatoriMenubar "Open UI" submenu (e.g. "Open UI /outcomes") for quick access.

### 4.4 No API contract change

- No new or changed fields in `POST /v1/agent/outcome` or `GET /v1/health`.
- No new public API endpoints required for DoD; optional internal/operator endpoint is out of scope for "API contract unchanged".

---

## 5. Rollout and board-level plan

- **Phase 1 (this card):** Implement Option A (route + queries + summary cards + optional platform breakdown). Document in runbook. Acceptance: operator can open `/outcomes` and see sent_as_is / edited_then_sent counts and ratios over 7 d and 30 d.
- **Phase 2 (follow-up if needed):** Optional `GET /v1/operator/metrics` for scripts/automation; or add simple time-bucketed series (e.g. by day) for a minimal trend chart.
- **Board:** Move #280 from IDEA BANK to Backlog when starting; then to In Progress (NOW) when implementing; to Done when acceptance criteria and evidence are met.

---

## 6. Acceptance criteria (DoD) mapping

| Criterion | How met |
|-----------|---------|
| Defines core metrics and data sources | §2 (metrics table + delivery_events / learning_events). |
| Includes board-level rollout plan | §5 (Phase 1 = this card; Phase 2 optional). |
| Keeps existing API contract unchanged | §4.4; no change to existing endpoints. |

---

## 7. Files to touch (implementation)

| File | Change |
|------|--------|
| `ui/app.py` | New `@app.get("/outcomes")` (or `/operator`); helper to run aggregation queries; HTML rendering with layout(). |
| `docs/07-runbooks/runbook-local.md` | Short subsection "Operator dashboard" with path and metric definitions. |
| `docs/00-overview/README.md` or menu-user-guide | Link to Outcomes/Operator from UI nav or menu if added. |
| Optional: `tools/macos/HatoriMenubar/main.swift.template` | Add "Open UI /outcomes" if menu is extended. |

No migration; no API app changes except optional read-only endpoint in Phase 2.

---

## 8. Delivery plan (task breakdown)

| # | Task | Owner | Acceptance | Deps |
|---|------|--------|------------|------|
| 1 | **Define metrics and queries** | Dev | SQL for delivery counts (by status, last 7d/30d), approval/edit ratio, optional by platform and learning_events counts; documented in LLD §2 and §4.2. | — |
| 2 | **Add GET /outcomes route** | Dev | ✅ Route in ui/app.py; run aggregation queries; return HTML with layout(); show sent_as_is, edited_then_sent, not_sent counts and approval/edit ratio for 7d and 30d. | 1 |
| 3 | **Add platform breakdown (optional)** | Dev | ✅ Table by delivery_events.platform with counts per status (last 30 d). | 2 |
| 4 | **Nav link** | Dev | ✅ Link "Outcomes" in layout nav next to Learning / Interactions. | 2 |
| 5 | **Runbook and docs** | Dev | ✅ runbook-local.md: "Operator dashboard (Outcomes)" subsection; menu-user-guide: "Open UI /outcomes". | 2 |
| 6 | **DoD evidence and SSOT** | Dev | Screenshot or curl + HTML snippet; post evidence on #280; move card to Done. | 1–5 |

**Suggested order:** 1 → 2 → 4 → 5 → 6; 3 can be in same PR as 2 or follow-up.

**Definition of done for #280:** Operator can open `/outcomes` (or linked nav), see sent_as_is / edited_then_sent / not_sent counts and approval and edit ratios for last 7 and 30 days; core metrics and data sources documented in LLD; runbook updated; API contract unchanged; evidence on issue and card moved to Done.
