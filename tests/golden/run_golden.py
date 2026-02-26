import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "golden" / "fixtures" / "offline_playbook.txt"


def run(cmd: list[str], expect_ok: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if expect_ok and proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc


def run_cli(args: list[str], expect_ok: bool = True) -> subprocess.CompletedProcess:
    return run([sys.executable, "-m", "hatori.cli", *args], expect_ok=expect_ok)


def run_cli_json(args: list[str]) -> dict:
    proc = run_cli(args, expect_ok=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from CLI for args={args}\nOUT:\n{proc.stdout}\nERR:\n{proc.stderr}") from exc


def db_scalar(sql: str) -> str:
    proc = run(["./tools/scripts/db_psql.sh", "-t", "-A", "-c", sql], expect_ok=True)
    return proc.stdout.strip()


def assert_true(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def test_01_ask_json_shape() -> None:
    out = run_cli_json(["ask", "How should I use the charter?", "--json"])
    required = {
        "connectivity_state",
        "classification",
        "answer",
        "evidence",
        "assumptions",
        "next_actions",
        "memory_patch",
        "learning_log",
        "interaction_user_id",
        "interaction_agent_id",
    }
    assert_true(required.issubset(set(out.keys())), "Missing required ask JSON fields")


def test_02_connectivity_offline() -> None:
    out = run_cli_json(["ask", "What is today's market price?", "--json"])
    assert_true(out["connectivity_state"] == "OFFLINE", "Connectivity state must be OFFLINE")


def test_03_text_template_sections() -> None:
    proc = run_cli(["ask", "How should I use the charter?"])
    text = proc.stdout
    sections = [
        "1) Connectivity State: OFFLINE",
        "2) Answer / Recommendation",
        "3) Evidence & Sources",
        "4) Assumptions & Uncertainties",
        "5) Next Actions",
        "6) Memory Patch",
        "7) Learning Log (J)",
    ]
    for section in sections:
        assert_true(section in text, f"Missing template section: {section}")


def test_04_memory_patch_default() -> None:
    out = run_cli_json(["ask", "How should I proceed?", "--json"])
    assert_true(out["memory_patch"] == "No memory changes.", "Default ask should not write memory")


def test_05_interaction_logging() -> None:
    before = int(db_scalar("SELECT count(*) FROM interaction_events;"))
    run_cli_json(["ask", "How do I check pending records?", "--json"])
    after = int(db_scalar("SELECT count(*) FROM interaction_events;"))
    assert_true(after == before + 2, f"Ask should log 2 interactions, got delta={after - before}")


def test_06_done_signal_learning() -> None:
    before = int(db_scalar("SELECT count(*) FROM learning_events WHERE kind='ImplicitPositive';"))
    out = run_cli_json(["ask", "This helped, done", "--done", "--json"])
    after = int(db_scalar("SELECT count(*) FROM learning_events WHERE kind='ImplicitPositive';"))
    assert_true(after == before + 1, "--done should log one ImplicitPositive event")
    assert_true("ImplicitPositive" in out["learning_log"], "Learning log should mention ImplicitPositive")


def test_07_ingest_creates_artefact() -> None:
    before = int(db_scalar("SELECT count(*) FROM artefacts;"))
    out = run_cli_json(["ingest", str(FIXTURE), "--json"])
    after = int(db_scalar("SELECT count(*) FROM artefacts;"))
    assert_true(out["artefacts_created"] >= 1, "ingest should create artefact")
    assert_true(after == before + 1, "Artefact count should increase by 1 for fixture ingest")


def test_08_ingest_creates_chunks() -> None:
    before = int(db_scalar("SELECT count(*) FROM embeddings;"))
    out = run_cli_json(["ingest", str(FIXTURE), "--json"])
    after = int(db_scalar("SELECT count(*) FROM embeddings;"))
    assert_true(out["chunks_created"] >= 1, "ingest should create chunks")
    assert_true(after > before, "Embedding chunk count should increase")


def test_09_search_keyword() -> None:
    out = run_cli_json(["search", "NightlyWarmupChecklistToken", "--json", "--limit", "5"])
    assert_true(len(out["results"]) >= 1, "search should return at least one result")
    text = json.dumps(out, ensure_ascii=False)
    assert_true("NightlyWarmupChecklistToken" in text, "search should surface fixture token")


def test_10_citations_are_real_and_no_web_claims() -> None:
    out = run_cli_json(["ask", "NightlyWarmupChecklistToken steps", "--json"])
    for e in out.get("evidence", []):
        citation = e.get("citation", "")
        if citation.startswith("pks:"):
            rid = citation.split(":", 1)[1]
            exists = db_scalar(f"SELECT count(*) FROM pks_records WHERE id='{rid}';")
            assert_true(int(exists) == 1, f"Missing cited PKS record: {rid}")
        elif citation.startswith("emb:"):
            cid = citation.split(":", 1)[1].replace("'", "''")
            exists = db_scalar(f"SELECT count(*) FROM embeddings WHERE chunk_id='{cid}';")
            assert_true(int(exists) >= 1, f"Missing cited embedding chunk: {cid}")
        else:
            raise AssertionError(f"Unexpected citation prefix: {citation}")

    text = json.dumps(out, ensure_ascii=False).lower()
    assert_true("http://" not in text and "https://" not in text, "Offline ask output must not include web links")
    assumptions_text = " ".join(out.get("assumptions", []))
    assert_true("Not verified (offline)" in assumptions_text, "Offline disclaimer missing")


def main() -> None:
    # Deterministic state for golden tests.
    run(["./tools/scripts/db_reset.sh"], expect_ok=True)

    tests = [
        test_01_ask_json_shape,
        test_02_connectivity_offline,
        test_03_text_template_sections,
        test_04_memory_patch_default,
        test_05_interaction_logging,
        test_06_done_signal_learning,
        test_07_ingest_creates_artefact,
        test_08_ingest_creates_chunks,
        test_09_search_keyword,
        test_10_citations_are_real_and_no_web_claims,
    ]

    failures: list[str] = []
    for idx, test_fn in enumerate(tests, start=1):
        try:
            test_fn()
            print(f"PASS {idx:02d} {test_fn.__name__}")
        except Exception as exc:
            failures.append(f"FAIL {idx:02d} {test_fn.__name__}: {exc}")

    if failures:
        print("\n".join(failures))
        raise SystemExit(1)

    print(f"PASS: golden tests ({len(tests)} cases)")


if __name__ == "__main__":
    main()
