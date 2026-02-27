<p align="center">
  <img src="docs/assets/hatori-logo.svg" alt="{hatori} logo" width="140" />
</p>

<h1 align="center">{hatori}</h1>
<p align="center"><strong>Local-first personal agent with UI + API, auditable learning, and retrieval over your own knowledge.</strong></p>

<p align="center">
  <a href="https://github.com/moldovancsaba/hatori/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/moldovancsaba/hatori/ci.yml?branch=main&label=CI&style=for-the-badge" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-v0.6.0-2563EB?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux-0F172A?style=for-the-badge" alt="Platform">
  <img src="https://img.shields.io/badge/api-v1-0EA5E9?style=for-the-badge" alt="API v1">
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#installation">Installation</a> •
  <a href="#run-modes">Run Modes</a> •
  <a href="#api-and-integration">API & Integration</a> •
  <a href="#documentation-map">Docs</a>
</p>

## Product Overview

`{hatori}` is an offline-first assistant platform designed for two-way operation:

- You chat with `{hatori}` in the local UI (`8093`) and teach through real interactions.
- External apps call the API (`8094`) to ingest content, request replies, and report delivery outcomes (`sent_as_is` / `edited_then_sent`) so `{hatori}` learns from what was actually sent.

Core capabilities:
- Local UI chat and history
- API-first integration for upstream apps
- RAG pipeline with PostgreSQL + `pgvector`
- Auditable learning loop (`learning_events`, `delivery_events`)
- Model gateway strategy (MLX preferred, Ollama fallback)
- Localhost-first security and collision-safe service orchestration

## Why Teams Use It

- Local and private by default
- No hidden cloud dependency for base operation
- Reliable ingestion/reply/outcome loop for “learn from real sends” behavior
- Clear contract for integrations (idempotency + auth + rate limits)

## Quick Start

```bash
git clone https://github.com/moldovancsaba/hatori.git
cd hatori
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r ui/requirements.txt
./tools/scripts/hatori_env_init.sh
make run
```

Open:
- UI: `http://127.0.0.1:8093/chat`
- API health: `http://127.0.0.1:8094/v1/health`

## Installation

### Prerequisites

Required:
- Python 3.11+
- Docker engine (or Colima on macOS)
- Bash-compatible shell

Optional:
- Ollama (recommended local generator fallback)
- MLX-LM (Apple Silicon MLX backend)
- Node.js (for `clients/hatori-client` examples)

### Environment Bootstrap

Create local env + token:

```bash
./tools/scripts/hatori_env_init.sh
```

File created:
- `~/.config/hatori/hatori.env` (permissions: `600`)

Default keys include:
- `HATORI_API_TOKEN`
- `UI_PORT=8093`
- `API_PORT=8094`
- `HATORI_GENERATOR_ORDER=mlx,ollama`

### Database

```bash
make up
```

This starts local Postgres (`pgvector/pgvector:pg16`) container `hatori-pg`.

## Run Modes

### 1) Foreground local stack

```bash
make run
```

Starts/reuses DB + API + UI with safe port ownership checks.

### 2) Background macOS service (auto-start friendly)

```bash
make install-service
make service-status
make service-logs
```

Stop only `{hatori}` listeners:

```bash
make stop
```

Uninstall:

```bash
make uninstall-service
```

### 3) macOS menu bar app

```bash
make install-menubar-app
make run-menubar-app
```

App path:
- `~/Applications/HatoriMenu.app`

## API and Integration

Canonical API contract:
- [`docs/10-api-contracts/hatori-api-v1.md`](docs/10-api-contracts/hatori-api-v1.md)

Integration guide for external apps:
- [`docs/12-reply-integration/README.md`](docs/12-reply-integration/README.md)

Local operations runbook:
- [`docs/07-runbooks/runbook-local.md`](docs/07-runbooks/runbook-local.md)

### Stable API Endpoints (v1)

- `GET /v1/health`
- `POST /v1/agent/respond`
- `POST /v1/agent/feedback`
- `POST /v1/agent/outcome`
- `POST /v1/ingest/event`
- `POST /v1/artefacts/upload`
- `POST /v1/artefacts/ingest_path` (default disabled)
- `GET /v1/search`

### WebSocket Status

Current stable contract is HTTP-only. No public WebSocket endpoint is exposed in v1.

## Security and Reliability

- Default bind: `127.0.0.1`
- API write auth: `X-Hatori-Token` (`HATORI_API_TOKEN`)
- Idempotency keys:
  - ingest: `external_event_id`
  - outcome: `external_outcome_id`
- Token-scoped rate limits on key endpoints
- Collision-safe startup:
  - reuse if `{hatori}` already owns the port
  - refuse if foreign process owns the port
  - never kill non-`{hatori}` services

## Validation and Testing

Run full suite:

```bash
make test
```

Run planning gate:

```bash
./tools/scripts/planning_check.sh
```

Run integration smoke:

```bash
make reply-smoke
```

## Versioning and Releases

Current version:
- `v0.6.0` (from [`VERSION`](VERSION))

Release and SemVer policy:
- [`docs/04-ops/versioning-release.md`](docs/04-ops/versioning-release.md)

Rule summary:
- Patch: fixes/docs/non-breaking internal updates
- Minor: backward-compatible features
- Major: breaking changes

## Repository Structure

- `api/` - API service
- `ui/` - UI service
- `hatori/` - core runtime and adapters
- `pks/` - schema and migrations
- `tools/` - scripts, launchd, menu app tooling
- `tests/` - golden tests and fixtures
- `docs/` - product, architecture, API, runbooks
- `clients/hatori-client/` - minimal TypeScript integration client

## Documentation Map

- Overview: [`docs/00-overview/README.md`](docs/00-overview/README.md)
- Architecture: [`docs/02-architecture/architecture.md`](docs/02-architecture/architecture.md)
- Data/PKS spec: [`docs/03-data/pks-spec.md`](docs/03-data/pks-spec.md)
- API contract: [`docs/10-api-contracts/hatori-api-v1.md`](docs/10-api-contracts/hatori-api-v1.md)
- Integration kit: [`docs/12-reply-integration/README.md`](docs/12-reply-integration/README.md)
- Security/threat model: [`docs/05-security/threat-model.md`](docs/05-security/threat-model.md)
- Evaluation: [`docs/06-evaluation/golden-tests.md`](docs/06-evaluation/golden-tests.md)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run:
   - `make test`
   - `./tools/scripts/planning_check.sh`
4. Open a PR with verification output

## License

No license file is currently included. Add a license before broad redistribution.
