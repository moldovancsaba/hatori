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
```bash
make run-ui
```

Open: http://127.0.0.1:8088

## Troubleshooting
- If you see `python-multipart` error:
  - `python -m pip install python-multipart`
- If `make run-ui` fails due to import errors:
  - `python -c "import ui.app as m; print(hasattr(m,'app'))"`
