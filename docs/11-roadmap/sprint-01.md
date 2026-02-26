# Sprint 01 — Runtime MVP (Offline-First)

Goal: convert the governance foundation into a usable daily runtime loop without breaking charter guarantees.

## Scope

1) `hatori ask "<question>"` offline runtime path
- Classifies request (`Daily task` / `Project work` / `System upkeep`)
- Retrieves local PKS + local chunk evidence
- Produces required default template sections
- Logs user+agent interactions to module I (`interaction_events`)
- Logs implicit positive to module J only when explicitly signaled (`--done`)

2) `hatori ingest <path>` local ingestion
- Registers artefact rows
- Chunks local text content and stores in `embeddings.content`
- Keeps `embedding` nullable for now (keyword-first retrieval baseline)

3) `hatori search "<query>"` local retrieval
- Keyword retrieval over PKS and ingested chunks
- Returns ranked local results with citations

4) Golden tests (10 cases)
- Offline gating assertions
- Output template presence assertions
- No fabricated source IDs
- Memory Patch behavior guard
- I/J logging behavior guard

## Acceptance Criteria

- `make test` passes end-to-end.
- `hatori ask` always returns offline-safe template with:
  - Connectivity State
  - Answer / Recommendation
  - Evidence & Sources
  - Assumptions & Uncertainties
  - Next Actions
  - Memory Patch
  - Learning Log (J)
- `hatori ingest` increases `artefacts` and `embeddings` rows for valid text files.
- `hatori search` returns local ranked matches for ingested keywords.
- `hatori ask --done` writes one low-confidence `ImplicitPositive` learning event.
- Delivery hygiene enforced:
  - docs updated
  - `VERSION` + `CHANGELOG.md` updated
  - all changes committed
  - pushed to `origin/main`

## Verification Commands

```bash
make up
make reset
make test

python -m hatori.cli ask "How should I use the charter?"
python -m hatori.cli ingest tests/golden/fixtures/offline_playbook.txt --json
python -m hatori.cli search "NightlyWarmupChecklistToken" --json
python -m hatori.cli ask "NightlyWarmupChecklistToken steps" --json
```
