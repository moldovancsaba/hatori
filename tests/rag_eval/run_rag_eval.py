#!/usr/bin/env python3
"""
RAG retrieval eval — Phase 1 for #350.

Runs after `make reset` + seed, before the golden suite (see Makefile `test` target).
Metrics: recall@k (binary per case), MRR (mean reciprocal rank of first relevant hit).

Usage:
  cd repo && . .venv/bin/activate && python tests/rag_eval/run_rag_eval.py

Standalone (clean DB recommended):
  make reset && python tests/rag_eval/run_rag_eval.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = Path(__file__).resolve().parent / "cases.json"


def run(cmd: list[str], *, cwd: Path | None = None, expect_ok: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True)
    if expect_ok and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def db_scalar(sql: str) -> str:
    proc = run(
        ["./tools/scripts/db_psql.sh", "-t", "-A", "-c", sql],
        expect_ok=True,
    )
    return proc.stdout.strip()


def run_cli_json(args: list[str]) -> dict:
    proc = run([sys.executable, "-m", "hatori.cli", *args], expect_ok=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from CLI args={args}\nOUT:\n{proc.stdout}") from exc


def sql_escape(value: str) -> str:
    return value.replace("'", "''")


def load_cases() -> list[dict[str, Any]]:
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("cases.json must be a JSON array")
    return data


def resolve_uri_pattern(path_rel: str) -> str:
    return str((ROOT / path_rel).resolve())


def ingest_paths(paths_rel: list[str]) -> None:
    for rel in paths_rel:
        p = ROOT / rel
        if not p.is_file():
            raise SystemExit(f"Ingest path missing: {p}")
        out = run_cli_json(["ingest", str(p.resolve()), "--json"])
        if int(out.get("artefacts_created") or 0) < 1:
            raise SystemExit(f"Ingest created no artefacts for {rel}: {out}")


def artefact_id_for_uri_substring(fragment: str) -> str:
    # Match seeded artefact by path fragment (uri is absolute path on disk).
    q = sql_escape(fragment)
    return db_scalar(
        f"SELECT id::text FROM artefacts WHERE uri LIKE '%{q}%' ORDER BY created_at DESC LIMIT 1;"
    )


def insert_pks_case(pks: dict[str, Any]) -> str:
    rid = str(uuid.uuid4())
    mod = sql_escape(str(pks.get("module", "A")))
    title = sql_escape(str(pks["title"]))
    body = sql_escape(str(pks["body"]))
    status = sql_escape(str(pks.get("status", "Approved")))
    sql = (
        "INSERT INTO pks_records (id,module,title,body,status,provenance,confidence,scope) "
        f"VALUES ('{rid}'::uuid,'{mod}','{title}','{body}','{status}','User','High','Personal');"
    )
    db_scalar(sql)
    return rid


def first_relevant_rank(results: list[dict[str, Any]], *, artefact_id: str | None, pks_id: str | None) -> int | None:
    for i, row in enumerate(results):
        if artefact_id and row.get("artefact_id") == artefact_id:
            return i + 1
        cit = row.get("citation") or ""
        if pks_id and cit == f"pks:{pks_id}":
            return i + 1
    return None


def eval_case(case: dict[str, Any]) -> dict[str, Any]:
    cid = case["id"]
    k = int(case.get("k", 10))
    query = str(case["query"])
    ingest_paths(case.get("ingest") or [])

    expected_aid: str | None = None
    expected_pks: str | None = None

    if "expect_uri_contains" in case:
        expected_aid = artefact_id_for_uri_substring(str(case["expect_uri_contains"]))
        if not expected_aid:
            return {
                "id": cid,
                "ok": False,
                "recall": 0.0,
                "mrr": 0.0,
                "error": f"No artefact found for uri fragment {case['expect_uri_contains']!r}",
            }

    if "pks" in case:
        expected_pks = insert_pks_case(case["pks"])

    payload = run_cli_json(["search", query, "--json", "--limit", str(k)])
    results = payload.get("results") or []
    rank = first_relevant_rank(results, artefact_id=expected_aid, pks_id=expected_pks)
    if rank is not None and rank <= k:
        return {
            "id": cid,
            "ok": True,
            "recall": 1.0,
            "mrr": 1.0 / rank,
            "rank": rank,
            "k": k,
        }
    return {
        "id": cid,
        "ok": False,
        "recall": 0.0,
        "mrr": 0.0,
        "rank": None,
        "k": k,
        "error": "Expected artefact or PKS citation not in top-k results",
        "got_citations": [r.get("citation") for r in results[:5]],
    }


def main() -> int:
    if not CASES_PATH.is_file():
        print("FAIL: cases.json missing", file=sys.stderr)
        return 1

    cases = load_cases()
    rows: list[dict[str, Any]] = []
    for case in cases:
        rows.append(eval_case(case))

    n = len(rows)
    mean_recall = sum(r["recall"] for r in rows) / n if n else 0.0
    mean_mrr = sum(r["mrr"] for r in rows) / n if n else 0.0
    failed = [r for r in rows if not r["ok"]]

    print("RAG eval summary")
    print(f"  cases: {n}")
    print(f"  mean recall@k: {mean_recall:.3f}")
    print(f"  mean MRR:      {mean_mrr:.3f}")
    for r in rows:
        extra = ""
        if r.get("rank"):
            extra = f" rank={r['rank']}"
        if not r["ok"]:
            extra += f" ERROR: {r.get('error', '')} citations_preview={r.get('got_citations')}"
        print(f"  - {r['id']}: {'PASS' if r['ok'] else 'FAIL'}{extra}")

    if failed:
        print("\nFAIL: RAG eval", file=sys.stderr)
        return 1
    print("\nPASS: RAG eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
