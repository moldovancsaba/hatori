status:
	./tools/scripts/db_status.sh

psql:
	./tools/scripts/db_psql.sh -c "\dt"

seed:
	./tools/scripts/db_seed.sh

reset:
	./tools/scripts/db_reset.sh

test:
	$(MAKE) reset
	./tools/scripts/db_lock_contention_test.sh
	./tools/scripts/self_test.sh
	./tools/scripts/dod_gate.sh
	. .venv/bin/activate && python tests/golden/run_golden.py

.PHONY: run-ui
run-ui:
	. .venv/bin/activate && python -m uvicorn ui.app:app --host 127.0.0.1 --port 8088

.PHONY: run-ui-hatori
run-ui-hatori:
	@PORT_VAL=$${UI_PORT:-$${PORT:-23571}}; \
	ORDER=$${HATORI_GENERATOR_ORDER:-mlx,ollama}; \
	NEED_OLLAMA=0; \
	if printf '%s' "$$ORDER" | tr '[:upper:]' '[:lower:]' | grep -q 'ollama'; then NEED_OLLAMA=1; fi; \
	if [ "$${HATORI_MODEL:-}" = "ollama" ] || [ -n "$${HATORI_OLLAMA_MODEL:-}" ] || [ -n "$${HATORI_OLLAMA_URL:-}" ]; then NEED_OLLAMA=1; fi; \
	if [ "$$NEED_OLLAMA" = "1" ]; then ./tools/scripts/ensure_ollama.sh; fi; \
	./tools/scripts/ensure_service_port.sh "$$PORT_VAL" ui ". .venv/bin/activate && python -m uvicorn ui.app:app --host 127.0.0.1 --port $$PORT_VAL"

.PHONY: run-api
run-api:
	@API_PORT_VAL=$${API_PORT:-23572}; \
	HOST=$${HATORI_API_BIND:-127.0.0.1}; \
	if [ "$$HOST" != "127.0.0.1" ] && [ "$$HOST" != "localhost" ] && [ "$$HOST" != "::1" ] && [ -z "$${HATORI_API_ALLOW_CIDRS:-}" ]; then \
	  echo "Refusing non-loopback bind without HATORI_API_ALLOW_CIDRS"; \
	  exit 1; \
	fi; \
	./tools/scripts/ensure_service_port.sh "$$API_PORT_VAL" api ". .venv/bin/activate && HATORI_API_TOKEN=\$${HATORI_API_TOKEN:?set HATORI_API_TOKEN} python -m uvicorn api.app:app --host $$HOST --port $$API_PORT_VAL"

.PHONY: run
run:
	@if command -v colima >/dev/null 2>&1; then colima start >/dev/null 2>&1 || true; docker context use colima >/dev/null 2>&1 || true; fi
	$(MAKE) up
	@API_PORT=$${API_PORT:-23572}; \
	( $(MAKE) run-api >/tmp/hatori-run-api.log 2>&1 & ); \
	sleep 1; \
	$(MAKE) run-ui-hatori

.PHONY: stop-ui
stop-ui:
	./tools/scripts/stop_hatori.sh ui

.PHONY: stop-api
stop-api:
	./tools/scripts/stop_hatori.sh api

.PHONY: stop
stop:
	./tools/scripts/stop_hatori.sh

.PHONY: install-service
install-service:
	./tools/scripts/hatori_env_init.sh
	@mkdir -p "$$HOME/Library/LaunchAgents" "$$HOME/Library/Logs/Hatori"
	@python3 -c 'from pathlib import Path; home=Path.home(); repo=Path.cwd(); template=(repo / "tools" / "launchd" / "com.hatori.plist").read_text(encoding="utf-8"); out=template.replace("__HOME__", str(home)).replace("__REPO_ROOT__", str(repo)); target=home / "Library" / "LaunchAgents" / "com.hatori.plist"; target.write_text(out, encoding="utf-8"); print("Wrote", target)'
	@launchctl unload "$$HOME/Library/LaunchAgents/com.hatori.plist" >/dev/null 2>&1 || true
	@launchctl load -w "$$HOME/Library/LaunchAgents/com.hatori.plist"
	@echo "Service installed: com.hatori"

.PHONY: uninstall-service
uninstall-service:
	@launchctl unload "$$HOME/Library/LaunchAgents/com.hatori.plist" >/dev/null 2>&1 || true
	@rm -f "$$HOME/Library/LaunchAgents/com.hatori.plist"
	@echo "Service removed: com.hatori"

.PHONY: service-status
service-status:
	@launchctl list | grep com.hatori || echo "com.hatori not loaded"
	@curl -fsS "http://127.0.0.1:$${API_PORT:-23572}/v1/health" >/dev/null 2>&1 && echo "API health: ok" || echo "API health: unavailable"
	@curl -fsS "http://127.0.0.1:$${UI_PORT:-23571}/chat" >/dev/null 2>&1 && echo "UI health: ok" || echo "UI health: unavailable"

.PHONY: service-logs
service-logs:
	@tail -n 200 "$$HOME/Library/Logs/Hatori/hatori.log"

.PHONY: reply-smoke
reply-smoke:
	./tools/scripts/reply_smoke.sh

.PHONY: install-HatoriMenubar
install-HatoriMenubar:
	./tools/macos/HatoriMenubar/install_HatoriMenubar.sh

.PHONY: run-HatoriMenubar
run-HatoriMenubar:
	open "$$HOME/Applications/HatoriMenubar.app"

.PHONY: up
up:
	@docker ps -a --format "{{.Names}}" | grep -qx hatori-pg && docker start hatori-pg || docker run -d --name hatori-pg -e POSTGRES_PASSWORD=hatori -e POSTGRES_USER=hatori -e POSTGRES_DB=hatori -p 5432:5432 pgvector/pgvector:pg16

.PHONY: up-ci
up-ci:
	@docker ps -a --format "{{.Names}}" | grep -qx hatori-pg && docker start hatori-pg || docker run -d --name hatori-pg -e POSTGRES_PASSWORD=hatori -e POSTGRES_USER=hatori -e POSTGRES_DB=hatori pgvector/pgvector:pg16
	@echo "Waiting for Postgres readiness (hatori-pg)..."
	@for i in $$(seq 1 30); do docker exec hatori-pg pg_isready -U hatori -d hatori >/dev/null 2>&1 && break; sleep 1; done
	@docker exec hatori-pg pg_isready -U hatori -d hatori >/dev/null 2>&1 || (echo "FAIL: Postgres not ready in container hatori-pg"; exit 1)

.PHONY: down-ci
down-ci:
	@docker rm -f hatori-pg >/dev/null 2>&1 || true

.PHONY: bootstrap
bootstrap:
	./tools/scripts/hatori_bootstrap.sh

.PHONY: models-pull
models-pull:
	./tools/scripts/hatori_models_pull.sh

.PHONY: doctor
doctor:
	./tools/scripts/hatori_doctor.sh

.PHONY: integration-acceptance
integration-acceptance:
	./tools/scripts/integration_acceptance.sh

.PHONY: searxng-up
searxng-up:
	./tools/scripts/searxng_up.sh

.PHONY: searxng-down
searxng-down:
	./tools/scripts/searxng_down.sh

.PHONY: searxng-status
searxng-status:
	./tools/scripts/searxng_status.sh
