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

Service startup behavior:
- API/UI processes always source `~/.config/hatori/hatori.env` at runtime start; ports come from `UI_PORT`/`API_PORT` (defaults 23571/23572 if unset).
- API/UI startup is non-blocking with respect to Docker/DB bootstrap.
- If Docker/Colima is unavailable at login, service still starts API/UI and retries DB bootstrap in background.
- Health may show `DB: down/unknown` temporarily while API remains reachable.

**SSOT #339 (Startup hardening + MLX reliability)** — acceptance mapping:
- launchd starts API/UI even if Docker/Colima is down: `tools/scripts/hatori_service.sh` starts API/UI in loop; `try_bootstrap_docker_stack` is best-effort and does not block.
- API sources `hatori.env` at start: service invokes API with `set -a; . "$ENV_FILE"; set +a` before uvicorn.
- stop/restart honor ports from env: `tools/scripts/stop_hatori.sh` sources env and uses `UI_PORT`/`API_PORT`.
- `/v1/health` MLX state: `api/app.py` `_runtime_status()` returns `configured: true|false`; menu shows "n/a" when not configured (see menu-user-guide).
- MLX fallback: `tools/scripts/hatori_mlx_mode.sh` (on|off|status); runbook "MLX operational failover" and menu-user-guide "need temporary continuity while MLX is broken".

Menu bar control app (health + stop/restart/quit):

```bash
make install-HatoriMenubar
make run-HatoriMenubar
```

Installed app location:
- `~/Applications/HatoriMenubar.app`

Menu user guide:
- `docs/07-runbooks/menu-user-guide.md`

To auto-start the menu bar app on login:
1. Open macOS `System Settings`
2. Go to `General` -> `Login Items`
3. Click `+` and select `~/Applications/HatoriMenubar.app`

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
- 100+ golden tests for offline runtime behavior (including chat + upload UI flows)

Concurrency rule:
- Keep DB-mutating commands sequential (`make reset`, `make test`, `./tools/scripts/planning_check.sh`).
- If a second command starts while another holds the DB lock, it fails fast with `DB busy; retry`.

## Daily runtime commands

### Online search routing (SearXNG + local LLM synthesis)

Start local SearXNG:

```bash
make searxng-up
make searxng-status
```

Enable online routing in `~/.config/hatori/hatori.env`:

```bash
HATORI_ENABLE_ONLINE=1
HATORI_ONLINE_ROUTE_MODE=auto
HATORI_ONLINE_SYNTHESIS_MODE=direct
HATORI_SEARXNG_URL=http://127.0.0.1:8888
```

Restart service:

```bash
make install-service
```

Behavior:
- `HATORI_ONLINE_ROUTE_MODE=auto`: normal natural-language questions are routed through online retrieval.
- `HATORI_ONLINE_ROUTE_MODE=keyword`: only clearly online-intent questions are routed.
- `HATORI_ONLINE_ROUTE_MODE=off`: disables online retrieval path.
- `HATORI_ONLINE_SYNTHESIS_MODE=direct`: return sourced web synthesis directly (fast, default).
- `HATORI_ONLINE_SYNTHESIS_MODE=llm`: pass web snippets to local LLM for rewritten final response.
- Online synthesis uses a lightweight LLM lane (`retrieval_query_build`) for faster responses.

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

MLX operational failover switch:

```bash
tools/scripts/hatori_mlx_mode.sh status
tools/scripts/hatori_mlx_mode.sh off
make install-service
curl -sS http://127.0.0.1:23572/v1/health
tools/scripts/hatori_mlx_mode.sh on
make install-service
```

Behavior:
- `off` sets `HATORI_DISABLE_MLX=1` and rewires MLX writer lanes (`reply_write`, `plan_write`, `rewrite_polish`) to use the same Apertus model id via fallback backend.
- `on` sets `HATORI_DISABLE_MLX=0` and restores MLX eligibility in routing.

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

- Runtime connectivity is configurable: `OFFLINE`, `ONLINE-UNVERIFIED`, or `ONLINE-VERIFIED`.
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
- Service status shows `foreign process owns port`:
  - Cause: UI/API were started manually with `python -m uvicorn ...`, outside the launchd supervisor.
  - Recovery: run `make stop`, then start via menu `Start/Install Service` or `make install-service`.
- Service logs:
  - `make service-logs`
- API up but DB down after login:
  - Cause: Docker/Colima was unavailable during service bootstrap.
  - Verify API is reachable: `curl -sS http://127.0.0.1:23572/v1/health`
  - Restore Docker runtime: `colima start && docker context use colima && make up`
  - The supervisor retries DB bootstrap automatically; or trigger immediate retry with `make install-service`.
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

## Operator dashboard (Outcomes)

Track **sent_as_is** vs **edited_then_sent** and model-route quality (SSOT #280).

- **Path:** `http://127.0.0.1:${UI_PORT:-23571}/outcomes`
- **Metrics:** Delivery counts (sent_as_is, edited_then_sent, not_sent) for last 7 and 30 days; approval % and edit %; optional breakdown by `platform`; optional PositiveFeedback / NegativeFeedback counts from `learning_events`.
- **Data source:** `delivery_events` and `learning_events` (read-only). No API contract change.
- Nav: link "Outcomes" in the UI next to Learning / Interactions.

## Per-Task Model Routing (Final)

Route lanes:
- Writer: `reply_write`, `plan_write`, `rewrite_polish`
- Drafter: `classify_intent`, `extract_fields`, `context_pack`, `retrieval_query_build`, `edit_pattern_cluster`
- Judge: `answer_score`, `quality_gate`

Configure in `~/.config/hatori/hatori.env` using `HATORI_ROUTE_<TASK>_BACKEND|MODEL|FALLBACK_*` keys.

Recommended production setup:
- Writer primary: `mlx` + Apertus model id
- Writer fallback: `ollama:gemma2:2b`
- Drafter primary: `ollama:granite4:350m` (IBM Granite Nano — lightest; if you use `ollama run ibm/granite4:350m`, set `HATORI_ROUTE_*_MODEL=ibm/granite4:350m` in env)
- Drafter fallback: `ollama:gemma3:1b`
- Judge primary: `ollama:llama3.2:3b`

Bootstrap and model pull:

```bash
make bootstrap
make models-pull
make doctor
```

At launch (`make run` or the LaunchAgent service), the stack runs `ensure_ollama.sh` then `ensure_hatori_models.sh` so Ollama is up and required models (including Granite drafter) are pulled if missing — the agent is available when Hatori starts. `hatori_models_pull.sh` applies route defaults (e.g. `granite4:350m` for drafter) so even envs created before those defaults get the full model set.
