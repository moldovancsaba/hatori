# Integration Acceptance Spec (All External Integrators)

This document defines the minimum acceptance criteria for any external app integrating with `{hatori}`.

## Preconditions

- `{hatori}` API running locally: `http://127.0.0.1:23572`
- valid token in `~/.config/hatori/hatori.env` (`HATORI_API_TOKEN`)
- database reachable

## Required Pass Criteria

1. Health
- `GET /v1/health` returns `200`

2. Ingest idempotency
- first `POST /v1/ingest/event` -> success
- second identical request (same `external_event_id`) -> success with `duplicate=true`

3. Respond output shape
- `POST /v1/agent/respond` returns `200`
- response contains non-empty:
  - `assistant_interaction_id`
  - `assistant_message`

4. Outcome sent_as_is idempotency
- first `POST /v1/agent/outcome` (`status=sent_as_is`) -> success
- replay with same `external_outcome_id` -> `duplicate=true`

5. Outcome edited_then_sent validation
- request missing `original_text` or `final_sent_text` -> `400`

6. Outcome edited_then_sent correctness
- valid request including unified diff -> success
- replay with same `external_outcome_id` -> `duplicate=true`

7. Auth enforcement
- write endpoint without token -> `401`

## Run Command

```bash
make integration-acceptance
```

Implementation file:
- `tools/scripts/integration_acceptance.sh`

## CI Recommendation

- Run acceptance against a local ephemeral environment before release.
- Block release if acceptance script exits non-zero.
