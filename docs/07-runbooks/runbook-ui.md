# Runbook: UI

## Prereqs
- Docker running
- DB container: `hatori-pg` (see `make reset`)

## Setup
```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -r ui/requirements.txt
```

## Run

**Dev-only (UI only, fixed port):**
```bash
make run-ui
```
Open: http://127.0.0.1:8088

**Full stack / service (recommended):** Use `make run` or `make run-ui-hatori` so the UI uses `UI_PORT` from env (default 23571). See `docs/07-runbooks/runbook-local.md`.

## Troubleshooting
- If you see `python-multipart` error:
  - `python -m pip install python-multipart`
- If `make run-ui` fails due to import errors:
  - `python -c "import ui.app as m; print(hasattr(m,'app'))"`
