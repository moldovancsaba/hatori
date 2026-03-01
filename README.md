# Hatori

Local offline-first assistant runtime with API, UI, and menubar control.

## Current Runtime Ports
- UI: `127.0.0.1:23571`
- API: `127.0.0.1:23572`

Ports come from `~/.config/hatori/hatori.env` (`UI_PORT`, `API_PORT`).

## Start And Health
- Menubar LaunchAgent label: `com.hatori`
- Health endpoint: `GET /v1/health`

Current health contract includes:
- `runtime_status` (backend health/details for `mlx` and `ollama`)
- `task_model_routing` (`writer`, `drafter`, `judge`)
- `request_counts_last_minute`
- `generator_backends`, `generator_order`, `breaker`

## Reply Reliability
`POST /v1/agent/respond` now guarantees a user-facing fallback draft when model output is unsafe/unavailable.  
This prevents returning `unsafe model output removed` / raw local-model errors to `{reply}` end users.

## Menubar Service Supervision
LaunchAgent uses:
- `tools/scripts/hatori_service.sh`
- `tools/scripts/port_owner.sh`
- `tools/scripts/is_hatori_pid.sh`

Quick recovery:
```bash
launchctl kickstart -k gui/501/com.hatori
tail -n 80 ~/Library/Logs/Hatori/hatori.log
```

## Learnings (2026-03-01)
- Health schemas must be backward/forward compatible with toolbar parsers.
- Service supervisors must fail clearly when dependencies are missing.
- API user output must have deterministic fallback paths, not model-error passthrough.

## Planning And Tracking
- Project board SSOT: https://github.com/users/moldovancsaba/projects/1
- Product filter: `{hatori}`
