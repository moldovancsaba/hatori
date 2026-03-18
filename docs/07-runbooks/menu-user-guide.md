# {hatori} Menu User Guide

This guide explains what you can do from the macOS menu bar app (`HatoriMenubar`).

## What You See At The Top

- `{hatori} vX.Y.Z`: product name and currently installed app version.
- `Health: API up|down`: whether the local API is reachable.
- `DB: ok|fail  Primary: <runtime>/<model>`: DB status plus current primary generation runtime/model.
- `Runtimes: MLX up|down|n/a, Ollama up|down`: runtime service health. `n/a` means the runtime is not configured (e.g. no `HATORI_MLX_MODEL` or MLX disabled).
- `Writer / Drafter / Judge`: current task-lane routing, model, and fallback state.

## --- Basics ---

Use these daily.

- `Open UI /chat`
: opens the main conversation page.

- `Open UI /upload`
: upload files so `{hatori}` can index them.

- `Open UI /search`
: search memory and ingested knowledge.

- `Open API Health`
: opens raw `/v1/health` JSON for quick diagnostics.

- `Reply Smoke`
: runs end-to-end local smoke verification (`health -> respond -> outcome`).

## --- Advanced ---

Use these for operations and debugging.

- `Open UI /interactions`
: inspect user/assistant interaction event history.

- `Open UI /learning`
: inspect learning/outcome feedback records.

- `Restart Service`
: reinstalls/reloads local background service and restarts processes.

- `Stop Service`
: stops `{hatori}` listeners (safe stop path).

- `Start/Install Service`
: installs and starts launchd service for auto-start operation.

- `Service Logs`
: tails service logs and opens the current log file.

## Why Runtime + Model Lines Matter

`Ollama` and `MLX` are runtimes, not models.

- Runtime lines (`MLX`, `Ollama`) tell you if the engine is reachable. MLX shows `n/a` when not configured so you don’t see a misleading “down”.
- Lane lines (`Writer`, `Drafter`, `Judge`) tell you which model is used for each task type.

This helps you quickly diagnose:
- runtime down vs model missing,
- fallback activation,
- wrong model routing for a lane.

## Typical Troubleshooting

- `Health: API down`
: run `make service-status`, then `make install-service`.

- runtime shows `down`
: check local runtime (`ollama list`, MLX env/model config), then restart service.

- need temporary continuity while MLX is broken
: run `tools/scripts/hatori_mlx_mode.sh off`, then restart service (`make install-service`); MLX writer lanes are rewired to Apertus via fallback backend.

- MLX recovered and should be primary again
: run `tools/scripts/hatori_mlx_mode.sh on`, restart service, then confirm `/v1/health` shows `runtime_status.mlx.ok=true`.

- lane is `down` or unexpected model
: check `~/.config/hatori/hatori.env` route keys (`HATORI_ROUTE_<TASK>_*`), then restart.

## Related Docs

- Local runbook: `docs/07-runbooks/runbook-local.md`
- API contract: `docs/10-api-contracts/hatori-api-v1.md`
- Planning SSOT: `docs/11-roadmap/README.md`
