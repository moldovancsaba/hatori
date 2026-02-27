# Runbook: Local Runtime Loop

## Start services

```bash
cd /Users/moldovancsaba/Projects/hatori
make up
make reset
```

Single background install (auto-start on login):

```bash
make install-service
make service-status
```

Menu bar control app (health + stop/restart/quit):

```bash
make install-menubar-app
make run-menubar-app
```

Installed app location:
- `~/Applications/HatoriMenu.app`

To auto-start the menu bar app on login:
1. Open macOS `System Settings`
2. Go to `General` -> `Login Items`
3. Click `+` and select `~/Applications/HatoriMenu.app`

One-command foreground run (local terminal):

```bash
make run
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

Ollama adapter (fastest operational path; local/offline after model pull):

```bash
brew services start ollama
ollama pull llama3.2:3b
export HATORI_MODEL=ollama
export HATORI_OLLAMA_MODEL=llama3.2:3b
python -m hatori.cli model-smoke "Respond in one sentence"
```

Launcher defaults:
- `HATORI_MODEL=ollama`
- `HATORI_OLLAMA_MODEL=llama3.2:3b`

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
PORT=23571 make run-ui-hatori
```

Open:
- `http://127.0.0.1:23571/chat`
- `http://127.0.0.1:23571/upload`
- `http://127.0.0.1:23571/search`
- API health: `http://127.0.0.1:23572/v1/health`

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
- Ollama model smoke fails:
  - Verify `brew services start ollama`.
  - Verify local service responds on `http://127.0.0.1:11434/api/tags`.
  - Verify `HATORI_OLLAMA_MODEL` exists locally (`ollama list`).
- Port busy for UI/API:
  - Run `make stop` (stops only {hatori} listeners).
  - Re-run `make run` or `make install-service`.
  - If a non-{hatori} process owns the port, startup refuses and prints PID + CMD (no forced kill).
- Service logs:
  - `make service-logs`
- Reply integration smoke:
  - `make reply-smoke`

## API outcome loop (`{reply}` -> {hatori})

Load token:

```bash
source ~/.config/hatori/hatori.env
```

Ask {hatori}:

```bash
RESP=$(curl -s -X POST http://127.0.0.1:23572/v1/agent/respond \
  -H "Content-Type: application/json" \
  -H "X-Hatori-Token: $HATORI_API_TOKEN" \
  -d '{
    "conversation_id":"reply:thread-123",
    "message_id":"reply:msg-001",
    "sender_id":"reply:user-42",
    "message":"Szia! Tudsz segíteni egy rövid válasszal?",
    "metadata":{"platform":"imessage"}
  }')
AID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['assistant_interaction_id'])")
ORIG=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['assistant_message'])")
```

Outcome `sent_as_is`:

```bash
curl -s -X POST http://127.0.0.1:23572/v1/agent/outcome \
  -H "Content-Type: application/json" \
  -H "X-Hatori-Token: $HATORI_API_TOKEN" \
  -d "{
    \"external_outcome_id\":\"reply:outcome-001\",
    \"assistant_interaction_id\":\"$AID\",
    \"conversation_id\":\"reply:thread-123\",
    \"platform\":\"imessage\",
    \"status\":\"sent_as_is\"
  }"
```

Outcome `edited_then_sent` with unified diff:

```bash
FINAL="Szia! Persze — miben segíthetek pontosan?"
DIFF=$(python3 - <<'PY'
import difflib, os
orig = os.environ["ORIG"]
final = os.environ["FINAL"]
u = difflib.unified_diff(orig.splitlines(True), final.splitlines(True), fromfile="original", tofile="final")
print("".join(u))
PY
)

python3 - <<'PY'
import json, os, subprocess
payload = {
  "external_outcome_id":"reply:outcome-002",
  "assistant_interaction_id":os.environ["AID"],
  "conversation_id":"reply:thread-123",
  "platform":"imessage",
  "status":"edited_then_sent",
  "original_text":os.environ["ORIG"],
  "final_sent_text":os.environ["FINAL"],
  "diff":os.environ["DIFF"],
  "edit_reason":"shorter + more natural"
}
subprocess.run([
  "curl","-s","-X","POST","http://127.0.0.1:23572/v1/agent/outcome",
  "-H","Content-Type: application/json",
  "-H",f"X-Hatori-Token: {os.environ['HATORI_API_TOKEN']}",
  "-d",json.dumps(payload, ensure_ascii=False),
], check=True)
PY
```

Idempotency behavior:
- `external_outcome_id` is unique.
- Repeating the same payload returns the existing IDs and does not create duplicate `delivery_events` / `learning_events`.

## Per-Task Model Routing (Final)

Route lanes:
- Writer: `reply_write`, `plan_write`, `rewrite_polish`
- Drafter: `classify_intent`, `extract_fields`, `context_pack`, `retrieval_query_build`, `edit_pattern_cluster`
- Judge: `answer_score`, `quality_gate`

Configure in `~/.config/hatori/hatori.env` using `HATORI_ROUTE_<TASK>_BACKEND|MODEL|FALLBACK_*` keys.

Recommended production setup:
- Writer primary: `mlx` + Apertus model id
- Writer fallback: `ollama:gemma2:2b`
- Drafter primary: `ollama:gemma3:1b`
- Drafter fallback: `ollama:llama3.2:1b`
- Judge primary: `ollama:llama3.2:3b`

Bootstrap and model pull:

```bash
make bootstrap
make models-pull
make doctor
```
