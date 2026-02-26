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
- schema + seed self-checks
- 10 golden tests for offline runtime behavior

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

### Search local evidence

```bash
python -m hatori.cli search "query text"
python -m hatori.cli search "query text" --limit 10 --json
```

## Notes

- Current runtime mode is intentionally `OFFLINE`.
- Retrieval is keyword-first over:
  - `pks_records` (Approved by default)
  - `embeddings.content` from local ingestion
- `--allow-pending` can be used on `ask`/`search` when needed for review workflows.
