# {hatori} API v1 (Integration Contract)

This document is the canonical contract for external apps that send content to {hatori} for annotation and request reply generation.

## 1) Transport and Base URL

- Protocol: HTTP/1.1 JSON + multipart upload
- Base URL (default local): `http://127.0.0.1:23572`
- UI (separate service): `http://127.0.0.1:23571`

## 2) Authentication

- Header for authenticated endpoints:
  - `X-Hatori-Token: <token>`
- Token source on host:
  - `~/.config/hatori/hatori.env`
  - variable: `HATORI_API_TOKEN`

Auth rules:
- `GET /v1/health` is public (no token required).
- All write endpoints require token.
- `GET /v1/search` also requires token.

Unauthorized response:
```json
{ "detail": "unauthorized" }
```
Status: `401`

## 3) Endpoint Summary

- `GET /v1/health`
- `POST /v1/agent/respond`
- `POST /v1/agent/feedback`
- `POST /v1/agent/outcome`
- `POST /v1/ingest/event`
- `POST /v1/artefacts/upload` (multipart)
- `POST /v1/artefacts/ingest_path` (disabled by default)
- `GET /v1/search`

## 4) WebSocket Status

Current status: **no WebSocket endpoint is exposed**.

- There is no `/ws` or `/v1/stream` contract in v1.
- Use synchronous HTTP calls.
- If streaming is added later, it should be on API port `23572` (no new public port required).

## 5) Error Model

Common status codes:
- `200`: success
- `400`: validation error
- `401`: unauthorized
- `403`: forbidden (path ingest disabled / path outside allowlist)
- `413`: payload too large (`/v1/ingest/event` raw content > 200KB)
- `429`: rate limited (`{"detail":"rate_limited"}`)
- `5xx`: local runtime failure

## 6) Rate Limits (token-scoped, in-memory)

Defaults per token, per 60s window:
- `/v1/agent/respond`: `30/min`
- `/v1/ingest/event`: `120/min`
- `/v1/agent/outcome`: `120/min`

Override envs:
- `HATORI_RL_RESPOND_PER_MIN`
- `HATORI_RL_INGEST_PER_MIN`
- `HATORI_RL_OUTCOME_PER_MIN`

## 7) Idempotency Rules

### Required keys
- Ingest: `external_event_id` (required)
- Outcome: `external_outcome_id` (required)

### Behavior
- Replay of same ingest key returns same stored record and `duplicate=true`.
- Replay of same outcome key returns existing IDs and `duplicate=true`.
- Do not generate new IDs on retry from client side; reuse the same external idempotency key.

## 8) Endpoint Contracts

## 8.1 GET /v1/health

Response `200`:
```json
{
  "status": "ok",
  "version": "0.x.y",
  "ui_port": 23571,
  "api_port": 23572,
  "db": "ok",
  "model": "none|ollama|llamacpp",
  "model_name": "...",
  "request_counts_last_minute": {
    "respond": 1,
    "ingest": 3,
    "outcome": 2
  }
}
```

## 8.2 POST /v1/agent/respond

Auth: required

Request:
```json
{
  "conversation_id": "reply:<thread-id>",
  "message_id": "reply:<message-id>",
  "sender_id": "reply:<sender-id>",
  "message": "<text>",
  "received_at": "<optional-iso8601>",
  "mode": "chat",
  "external_request_id": "reply:<optional-idempotency>",
  "metadata": {
    "platform": "imessage|email|...",
    "channel": "optional",
    "extra": {}
  }
}
```

Response `200`:
```json
{
  "conversation_id": "reply:<thread-id>",
  "message_id": "reply:<message-id>",
  "user_interaction_id": "<uuid>",
  "assistant_interaction_id": "<uuid>",
  "assistant_message": "<user-facing text only>",
  "language": "hu|en|...",
  "connectivity_state": "OFFLINE",
  "sources": ["human-readable source labels"]
}
```

Notes:
- `assistant_message` is user-facing only; no internal scaffolding/IDs.
- If `external_request_id` is reused, server returns existing assistant row (idempotent replay behavior).
- If local model output is unavailable/unsafe/internal-scaffold, server returns a deterministic send-ready fallback message instead of exposing model runtime error text.

## 8.3 POST /v1/agent/feedback

Auth: required

Request:
```json
{
  "assistant_interaction_id": "<uuid>",
  "vote": "up|down",
  "category": "Relevance|Format|Accuracy|Evidence|Tone|Other",
  "comment": "optional",
  "external_request_id": "reply:<optional-idempotency>"
}
```

Response `200`:
```json
{ "learning_event_id": "<uuid>" }
```

## 8.4 POST /v1/agent/outcome

Auth: required

Request:
```json
{
  "external_outcome_id": "reply:<required-idempotency>",
  "assistant_interaction_id": "<uuid>",
  "conversation_id": "reply:<optional-thread-id>",
  "platform": "imessage|email|whatsapp|other",
  "recipient_id": "reply:<optional-recipient>",
  "status": "sent_as_is|edited_then_sent|not_sent",
  "original_text": "required when edited_then_sent",
  "final_sent_text": "required when edited_then_sent",
  "diff": "optional unified diff text",
  "edit_reason": "optional",
  "metadata": {}
}
```

Validation:
- `edited_then_sent` requires both `original_text` and `final_sent_text`.

Response `200`:
```json
{
  "delivery_event_id": "<uuid>",
  "learning_event_id": "<uuid>",
  "duplicate": false
}
```
Replay response (`duplicate=true`) returns existing IDs.

## 8.5 POST /v1/ingest/event

Auth: required

Request:
```json
{
  "external_event_id": "reply:<required-idempotency>",
  "kind": "email|imessage|doc|note|other",
  "conversation_id": "reply:<optional-thread>",
  "sender_id": "reply:<optional-sender>",
  "content": "<required raw text>",
  "metadata": {}
}
```

Limits:
- raw content max: `200KB`
- above limit => `413`, use `/v1/artefacts/upload`

Response `200`:
```json
{
  "stored": true,
  "interaction_id": "<uuid>",
  "artefact_id": null,
  "duplicate": false
}
```
Replay response sets `duplicate: true` and returns original IDs.

## 8.6 POST /v1/artefacts/upload

Auth: required

Content-Type: `multipart/form-data`

Fields:
- `external_event_id` (required)
- `kind` (required)
- `conversation_id` (optional)
- `sender_id` (optional)
- `file` (required)
- `metadata` (optional JSON string)

Response `200`:
```json
{
  "artefact_id": "<uuid>",
  "sha256": "<hex>",
  "chunks_created": 3
}
```

Notes:
- Supports idempotent replay via `external_event_id` (returns existing artefact/chunk counts).

## 8.7 POST /v1/artefacts/ingest_path

Auth: required

Request:
```json
{
  "external_event_id": "reply:<required-idempotency>",
  "kind": "doc|other",
  "path": "/absolute/local/path",
  "sha256": "optional",
  "metadata": {}
}
```

Guardrails:
- disabled unless `HATORI_ALLOW_PATH_INGEST=1`
- must pass allowlist in `HATORI_PATH_ALLOWLIST`

Responses:
- `403` if disabled/outside allowlist
- `200` with same payload shape as upload on success

## 8.8 GET /v1/search

Auth: required

Query params:
- `q` (required)
- `k` (optional, default 5, max 20)
- `conversation_id` (optional)

Response `200`:
```json
[
  {
    "snippet": "...",
    "source": "PKS Approved|LocalDoc",
    "title": "...",
    "path": "...",
    "score": 0.123
  }
]
```

No internal IDs are returned.

## 9) Recommended External App Sequence

1. Inbound message arrives
- call `/v1/ingest/event` with stable `external_event_id`

2. Need reply
- call `/v1/agent/respond`
- display `assistant_message`

3. User sends unchanged
- call `/v1/agent/outcome` with `status=sent_as_is`

4. User edits before send
- call `/v1/agent/outcome` with `status=edited_then_sent`
- include `original_text`, `final_sent_text`, and `diff` (unified diff)

## 11) Integrator Acceptance Gate

For any external team/channel integration, run:

```bash
make integration-acceptance
```

This enforces idempotency, auth, outcome validation, and replay behavior for the ingest/respond/outcome loop.

Related docs:
- `docs/12-reply-integration/README.md`
- `docs/12-reply-integration/integration-acceptance.md`

## 10) Minimal cURL Examples

Load token:
```bash
source ~/.config/hatori/hatori.env
```

Health:
```bash
curl -s http://127.0.0.1:23572/v1/health | python3 -m json.tool
```

Respond:
```bash
curl -s -X POST http://127.0.0.1:23572/v1/agent/respond \
  -H "Content-Type: application/json" \
  -H "X-Hatori-Token: $HATORI_API_TOKEN" \
  -d '{
    "conversation_id":"reply:thread-1",
    "message_id":"reply:msg-1",
    "sender_id":"reply:user-1",
    "message":"Szia! Tudsz segíteni?",
    "metadata":{"platform":"imessage"}
  }'
```

Outcome sent_as_is:
```bash
curl -s -X POST http://127.0.0.1:23572/v1/agent/outcome \
  -H "Content-Type: application/json" \
  -H "X-Hatori-Token: $HATORI_API_TOKEN" \
  -d '{
    "external_outcome_id":"reply:outcome-1",
    "assistant_interaction_id":"<assistant_id>",
    "status":"sent_as_is",
    "platform":"imessage"
  }'
```

## 11) Compatibility Notes

- Contract version: v1 (`/v1/*`)
- Keep token auth and localhost bind defaults unchanged.
- No WebSocket contract in v1.

## 13) Internal Model Routing

For v1 endpoints, model execution is routed internally by task class:
- writer tasks for user-facing responses
- drafter tasks for internal context preparation
- judge tasks for scoring/quality operations

This routing is configured via `HATORI_ROUTE_*` environment variables and does not change the public API contract.
