# Integrating External Apps with {hatori}

This guide is for any product/team/service integrating with `{hatori}` API (not only `{reply}`).

Canonical API contract:
- `docs/10-api-contracts/hatori-api-v1.md`

## Integration Loop (Required)

1. Ingest message/context
- `POST /v1/ingest/event`
- required: `external_event_id` (idempotency)

2. Request response
- `POST /v1/agent/respond`
- required: `conversation_id`, `message_id`, `message`
- returns `assistant_message` + `assistant_interaction_id`

3. Report real send outcome
- `POST /v1/agent/outcome`
- required: `external_outcome_id` (idempotency)
- `sent_as_is` -> positive signal
- `edited_then_sent` -> negative signal + correction target

For `edited_then_sent`, send:
- `original_text`
- `final_sent_text`
- `diff` (unified diff format)

## Idempotency Rules (Non-negotiable)

- Ingest idempotency key: `external_event_id`
- Outcome idempotency key: `external_outcome_id`
- Retries must reuse the same key.
- Server replay behavior must return `duplicate=true` and avoid duplicate writes.

## Error Handling

- `401`: missing/invalid `X-Hatori-Token`
- `400`: validation failure
- `413`: ingest payload too large for raw ingest (switch to upload)
- `429`: rate limited (retry with backoff)
- `5xx`: temporary local dependency failure (retry with backoff)

Reply generation resilience note:
- `POST /v1/agent/respond` is expected to return a send-ready `assistant_message` even when the local model path is unstable.
- Internal model/runtime text (for example `Local model error: ...`) must not be surfaced to `{reply}` users.

## Security

- Token source: `~/.config/hatori/hatori.env`
- Header: `X-Hatori-Token`
- Default local API URL: `http://127.0.0.1:23572`
- Keep `{hatori}` localhost-only by default.

## Acceptance Gate for Integrator Teams

Run this before production rollout:

```bash
make integration-acceptance
```

This validates end-to-end:
- health endpoint reachable
- ingest idempotency (`duplicate=true` on replay)
- respond returns `assistant_interaction_id` + `assistant_message`
- outcome `sent_as_is` idempotency
- outcome `edited_then_sent` strict validation
- outcome `edited_then_sent` with unified diff + idempotency
- unauthorized write returns `401`

## Channel Expansion Notes

For each new channel (email/whatsapp/etc), keep the same contract:
- ingest -> respond -> outcome
- stable idempotency keys
- unified diff on edits

Recommended for large content/attachments:
- use `POST /v1/artefacts/upload` instead of large raw ingest payloads.
