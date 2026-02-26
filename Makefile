status:
	./tools/scripts/db_status.sh

psql:
	./tools/scripts/db_psql.sh -c "\dt"

seed:
	./tools/scripts/db_seed.sh

reset:
	./tools/scripts/db_reset.sh

test:
	./tools/scripts/self_test.sh
	. .venv/bin/activate && python tests/golden/run_golden.py

.PHONY: run-ui
run-ui:
	. .venv/bin/activate && python -m uvicorn ui.app:app --host 127.0.0.1 --port 8088

.PHONY: up
up:
	@docker ps -a --format "{{.Names}}" | grep -qx hatori-pg && docker start hatori-pg || docker run -d --name hatori-pg -e POSTGRES_PASSWORD=hatori -e POSTGRES_USER=hatori -e POSTGRES_DB=hatori -p 5432:5432 pgvector/pgvector:pg16
