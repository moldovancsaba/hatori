# Reply <-> {hatori} Integration

Canonical API contract:
- `docs/10-api-contracts/hatori-api-v1.md`

## End-to-end loop

1. Ingest message/context into {hatori}
- `POST /v1/ingest/event`
- required: `external_event_id`

2. Ask {hatori} for a reply
- `POST /v1/agent/respond`
- returns `assistant_message`, `assistant_interaction_id`

3. Report what was actually sent
- `POST /v1/agent/outcome`
- `sent_as_is` -> positive signal
- `edited_then_sent` -> negative signal with `original_text`, `final_sent_text`, `diff` (unified diff)

## Idempotency

- Ingest: `external_event_id` must be stable per upstream event.
- Outcome: `external_outcome_id` must be stable per delivery outcome.
- Replays return `duplicate=true` and do not create new rows.

## Error handling

- `401 unauthorized`: missing/invalid `X-Hatori-Token`.
- `400`: request validation error.
- `413`: ingest payload too large for raw ingest (`/v1/ingest/event`), use upload endpoint.
- `429`: token-scoped rate limit exceeded; retry with backoff.
- `5xx`: local runtime dependency error; retry with backoff.

## Security

- Use `HATORI_API_TOKEN` from local env file (`~/.config/hatori/hatori.env`).
- Default base URL is localhost (`http://127.0.0.1:8094`).
- For multi-machine use, put API behind VPN/reverse proxy later; keep core service localhost by default.

## Quick flow

```text
reply inbound -> /v1/ingest/event
reply ask -> /v1/agent/respond
human send decision -> /v1/agent/outcome
```
