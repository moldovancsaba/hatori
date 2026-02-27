status:
	./tools/scripts/db_status.sh

psql:
	./tools/scripts/db_psql.sh -c "\dt"

seed:
	./tools/scripts/db_seed.sh

reset:
	./tools/scripts/db_reset.sh

test:
	./tools/scripts/db_lock_contention_test.sh
	./tools/scripts/self_test.sh
	./tools/scripts/dod_gate.sh
	. .venv/bin/activate && python tests/golden/run_golden.py

.PHONY: run-ui
run-ui:
	. .venv/bin/activate && python -m uvicorn ui.app:app --host 127.0.0.1 --port 8088

.PHONY: run-ui-hatori
run-ui-hatori:
	. .venv/bin/activate && python -m uvicorn ui.app:app --host 127.0.0.1 --port $${PORT:-8093}

.PHONY: run-api
run-api:
	. .venv/bin/activate && \
	HATORI_API_TOKEN=$${HATORI_API_TOKEN:?set HATORI_API_TOKEN} && \
	HOST=$${HATORI_API_BIND:-127.0.0.1} && \
	if [ "$$HOST" != "127.0.0.1" ] && [ "$$HOST" != "localhost" ] && [ "$$HOST" != "::1" ] && [ -z "$${HATORI_API_ALLOW_CIDRS:-}" ]; then \
	  echo "Refusing non-loopback bind without HATORI_API_ALLOW_CIDRS"; \
	  exit 1; \
	fi && \
	python -m uvicorn api.app:app --host "$$HOST" --port $${API_PORT:-8094}

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
