# hatori-client

Environment:
- `HATORI_BASE_URL` (default `http://127.0.0.1:8094`)
- `HATORI_API_TOKEN` (required)

Exports:
- `health()`
- `ingestEvent()`
- `respond()`
- `outcomeSentAsIs()`
- `outcomeEditedThenSent()`
- `toUnifiedDiff()`

Examples:
- `node examples/demo_ingest_and_respond.ts`
- `node examples/demo_outcome_sent_as_is.ts`
- `node examples/demo_outcome_edited_then_sent.ts`
