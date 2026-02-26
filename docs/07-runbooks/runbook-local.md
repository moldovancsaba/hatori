# Runbook: Local Runtime Loop

## Start services

```bash
cd /Users/moldovancsaba/Projects/reply-hatori
make up
make reset
```

## Validate baseline

```bash
make test
```

This runs:
- DB lock contention guard (`DB busy; retry` on concurrent mutation attempts)
- schema + seed self-checks
- 30 golden tests for offline runtime behavior (including semantic search and governance gates)

Concurrency rule:
- Keep DB-mutating commands sequential (`make reset`, `make test`, `./tools/scripts/planning_check.sh`).
- If a second command starts while another holds the DB lock, it fails fast with `DB busy; retry`.

## Daily runtime commands

### Ask (offline runtime)

```bash
python -m hatori.cli ask "How should I proceed with pending PKS updates?"
python -m hatori.cli ask "How should I proceed with pending PKS updates?" --json
python -m hatori.cli ask "This worked, done" --done --json
```

### Ingest local files

```bash
python -m hatori.cli ingest /path/to/local/file-or-folder
python -m hatori.cli ingest /path/to/local/file-or-folder --json
```

Optional local sentence-transformers backend (fully offline if model is local):

```bash
. .venv/bin/activate
python -m pip install -r hatori/requirements-embeddings.txt
export HATORI_EMBED_BACKEND=sentence-transformers
export HATORI_EMBED_MODEL_PATH=/absolute/path/to/local/model
```

### Search local evidence

```bash
python -m hatori.cli search "query text"
python -m hatori.cli search "query text" --limit 10 --json
```

## Notes

- Current runtime mode is intentionally `OFFLINE`.
- Retrieval merges keyword + semantic ranking over:
  - `pks_records` (Approved by default)
  - `embeddings.content` + `embeddings.embedding` (pgvector cosine distance)
- `--allow-pending` can be used on `ask`/`search` when needed for review workflows.

## Troubleshooting

- `DB busy; retry`:
  - Another DB-mutating command holds `/tmp/hatori_db.lockdir`.
  - Re-run after the current command exits.
- `psql failed` with vector operator errors:
  - Ensure DB schema was reset with `make reset` so `vector` extension is present.
- Missing optional sentence-transformers deps/model:
  - Either install `hatori/requirements-embeddings.txt` and set `HATORI_EMBED_MODEL_PATH`,
  - Or unset `HATORI_EMBED_BACKEND` to use deterministic `hash-v1`.
