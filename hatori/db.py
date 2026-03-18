"""
Shared DB runner for PKS/RAG modules. Uses docker exec + Postgres (same as CLI).
"""
import json
import os
import subprocess
from typing import Any

CID = os.environ.get("CID", "hatori-pg")


def esc_sql(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "''")


def jsonb_sql_literal(obj: dict[str, Any]) -> str:
    return "'" + esc_sql(json.dumps(obj, ensure_ascii=False)) + "'::jsonb"


def run_psql(sql: str) -> str:
    cmd = [
        "docker", "exec", "-i", CID,
        "psql", "-U", "hatori", "-d", "hatori", "-t", "-A", "-c", sql,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "psql failed")
    return r.stdout.strip()


def run_psql_json(sql: str) -> list[dict]:
    wrapped = f"SELECT COALESCE(json_agg(t), '[]'::json) FROM ({sql}) t;"
    out = run_psql(wrapped)
    if not out:
        return []
    return json.loads(out)
