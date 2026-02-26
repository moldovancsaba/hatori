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
- 50 golden tests for offline runtime behavior (including chat + upload UI flows)

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

Model selection:

```bash
export HATORI_MODEL=none
python -m hatori.cli model-smoke "Say OK"
```

Llama.cpp adapter (local/offline, user-provided model path):

```bash
export HATORI_MODEL=llamacpp
export HATORI_LLAMA_MODEL=/absolute/path/to/model.gguf
export HATORI_LLAMA_BIN=llama-cli
export HATORI_LLAMA_CTX=4096
export HATORI_LLAMA_THREADS=4
python -m hatori.cli model-smoke "Respond in one sentence"
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
python -m hatori.cli consistency-check --subset 8
```

### UI chat + upload flow

```bash
PORT=8093 make run-ui-hatori
```

Open:
- `http://127.0.0.1:8093/chat`
- `http://127.0.0.1:8093/upload`
- `http://127.0.0.1:8093/search`

Expected behavior:
- `/chat/send` creates user + assistant `interaction_events` scoped by `metadata.chat_id`.
- Chat feedback buttons create `learning_events` linked via `related_interaction_id` (assistant interaction ID).
- `/upload` stores files under `artefacts/uploads/`; `.txt`/`.md` also create chunk + vector rows in `embeddings`.

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
- Llama.cpp model smoke fails:
  - Verify `HATORI_MODEL=llamacpp`.
  - Verify `HATORI_LLAMA_MODEL` points to a local `.gguf` file.
  - Verify `llama-cli` is installed or set `HATORI_LLAMA_BIN` to the local executable path.
