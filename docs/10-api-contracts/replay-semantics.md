# Replay semantics and anti-duplication (#281)

**Scope:** Single-event ingest and outcome APIs. No batch endpoint in v1.

---

## 1) What counts as "bulk" in v1

- There is **no batch ingest endpoint** (e.g. no `POST /v1/ingest/batch`).
- "Bulk" or "many events" means **N separate requests**, each with its own `external_event_id` (ingest/upload) or `external_outcome_id` (outcome).
- Deduplication is **per request, per idempotency key**. There is no batch-level key (`batch_id`).

---

## 2) Idempotency key scope

| Endpoint | Key | Scope |
|----------|-----|--------|
| `POST /v1/ingest/event` | `external_event_id` (required) | One key per logical event. Reuse the same key on retry. |
| `POST /v1/artefacts/upload` | `external_event_id` (required) | One key per logical upload. Reuse on retry. |
| `POST /v1/artefacts/ingest_path` | `external_event_id` (required) | One key per path ingest. Reuse on retry. |
| `POST /v1/agent/outcome` | `external_outcome_id` (required) | One key per outcome. Reuse on retry. |
| `POST /v1/agent/respond` | `external_request_id` (optional) | One key per reply request. Reuse on retry. |

Keys are **opaque strings** (e.g. `reply:<uuid>`, `reply:thread-msg-123`). Client must generate and retain the same key for retries; do not create new keys for the same logical event/outcome.

---

## 3) Retry and replay behaviour

- **First request** with a given key: server creates the record(s), returns `200` with IDs and `duplicate: false` (where the contract includes `duplicate`).
- **Replay** (same key again): server **does not create new rows**. Returns `200` with the **existing** IDs and `duplicate: true` (for endpoints that expose it).
- **Client:** On retry (network failure, timeout), send the **same** request body including the same idempotency key. Do not generate a new key.

Endpoints that return `duplicate`:

- `POST /v1/ingest/event` — response includes `duplicate: true` on replay.
- `POST /v1/artefacts/upload` — response includes `duplicate: true` on replay (v1 contract).
- `POST /v1/agent/outcome` — response includes `duplicate: true` on replay.

---

## 4) Single-event API behaviour (backward compatible)

- **Ingest event:** Replay of same `external_event_id` returns same `interaction_id`, optional `artefact_id`, and `duplicate: true`. Exactly one row in `interaction_events` for that key (and one in `delivery_events` / artefacts if applicable).
- **Upload:** Replay of same `external_event_id` returns same `artefact_id`, `sha256`, `chunks_created`, and `duplicate: true`. No new artefact or embedding rows.
- **Outcome:** Replay of same `external_outcome_id` returns same `delivery_event_id`, `learning_event_id`, and `duplicate: true`. No new rows in `delivery_events` or `learning_events`.

Existing clients that ignore `duplicate` continue to work; new clients can use `duplicate` to avoid treating replay as a new creation.

---

## 5) Verification

- Golden tests: `test_96_api_ingest_event_idempotent`, `test_102_api_outcome_idempotency_blocks_duplicates`, and upload idempotency test assert:
  - First request: `duplicate: false`, new rows created.
  - Second request (same key): `duplicate: true`, same IDs returned, **no** additional DB rows for that key.
- Run `make test` and integration acceptance to confirm.

---

## 6) References

- API contract: [hatori-api-v1.md](hatori-api-v1.md) §7 Idempotency, §8.5–8.7.
- Delivery plan: [DELIVERY-PLAN-IDEA-BANK.md](../11-roadmap/DELIVERY-PLAN-IDEA-BANK.md) §2 #281.
