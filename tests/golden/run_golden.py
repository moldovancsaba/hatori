import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hatori.model import get_model_adapter
from hatori.prompts import CHARTER_PATH
from hatori.prompts import RUNTIME_SYSTEM_PATH
from hatori.prompts import TASK_TEMPLATE_PATH
from hatori.prompts import build_system_prompt
from hatori.prompts import build_task_prompt

FIXTURE = ROOT / "tests" / "golden" / "fixtures" / "offline_playbook.txt"
SEMANTIC_FIXTURE = ROOT / "tests" / "golden" / "fixtures" / "semantic_garage.txt"


def run(cmd: list[str], expect_ok: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    if expect_ok and proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc


def run_cli(args: list[str], expect_ok: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    return run([sys.executable, "-m", "hatori.cli", *args], expect_ok=expect_ok, env=env)


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


def sql_escape(value: str) -> str:
    return value.replace("'", "''")


def upsert_pending_record(module: str, title: str, body: str) -> str:
    rid = str(uuid.uuid4())
    sql = (
        "INSERT INTO pks_records (id,module,title,body,status,provenance,confidence,scope) "
        f"VALUES ('{rid}','{module}','{sql_escape(title)}','{sql_escape(body)}','Pending','User','High','Personal');"
    )
    db_scalar(sql)
    return rid


def upsert_approved_record(module: str, title: str, body: str) -> str:
    rid = str(uuid.uuid4())
    sql = (
        "INSERT INTO pks_records (id,module,title,body,status,provenance,confidence,scope) "
        f"VALUES ('{rid}','{module}','{sql_escape(title)}','{sql_escape(body)}','Approved','User','High','Personal');"
    )
    db_scalar(sql)
    return rid


def get_artefact_id_for_uri(uri: str) -> str:
    return db_scalar(f"SELECT id FROM artefacts WHERE uri='{sql_escape(uri)}' ORDER BY created_at DESC LIMIT 1;")


def ingest_fixture(path: Path) -> dict:
    return run_cli_json(["ingest", str(path), "--json"])


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
    out = ingest_fixture(FIXTURE)
    after = int(db_scalar("SELECT count(*) FROM artefacts;"))
    assert_true(out["artefacts_created"] >= 1, "ingest should create artefact")
    assert_true(after == before + 1, "Artefact count should increase by 1 for fixture ingest")


def test_08_ingest_creates_chunks() -> None:
    before = int(db_scalar("SELECT count(*) FROM embeddings;"))
    out = ingest_fixture(FIXTURE)
    after = int(db_scalar("SELECT count(*) FROM embeddings;"))
    assert_true(out["chunks_created"] >= 1, "ingest should create chunks")
    assert_true(after > before, "Embedding chunk count should increase")


def test_09_ingest_stores_non_null_vectors() -> None:
    ingest_fixture(FIXTURE)
    cnt = int(db_scalar("SELECT count(*) FROM embeddings WHERE embedding IS NOT NULL;"))
    assert_true(cnt >= 1, "Embeddings must store non-null vectors")


def test_10_embedding_metadata_has_embedder() -> None:
    ingest_fixture(FIXTURE)
    embedder = db_scalar("SELECT metadata->>'embedder' FROM embeddings ORDER BY created_at DESC LIMIT 1;")
    dim = db_scalar("SELECT metadata->>'embed_dim' FROM embeddings ORDER BY created_at DESC LIMIT 1;")
    assert_true(embedder != "", "Embedding metadata must include adapter name")
    assert_true(int(dim) > 0, "Embedding metadata must include positive dimension")


def test_11_search_keyword() -> None:
    out = run_cli_json(["search", "NightlyWarmupChecklistToken", "--json", "--limit", "5"])
    assert_true(len(out["results"]) >= 1, "search should return at least one result")
    text = json.dumps(out, ensure_ascii=False)
    assert_true("NightlyWarmupChecklistToken" in text, "search should surface fixture token")


def test_12_search_result_fields() -> None:
    out = run_cli_json(["search", "NightlyWarmupChecklistToken", "--json", "--limit", "5"])
    row = out["results"][0]
    assert_true("excerpt" in row and row["excerpt"] != "", "Result must include non-empty excerpt")
    assert_true("provenance" in row, "Result must include provenance")
    if row["citation"].startswith("emb:"):
        assert_true(bool(row.get("artefact_id")), "Embedding result must include artefact_id")


def test_13_ask_no_web_claims() -> None:
    out = run_cli_json(["ask", "NightlyWarmupChecklistToken steps", "--json"])
    text = json.dumps(out, ensure_ascii=False).lower()
    assert_true("http://" not in text and "https://" not in text, "Offline ask output must not include web links")
    assert_true("verified" not in text, "Offline ask must not claim verification")


def test_14_ask_citations_are_real() -> None:
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


def test_15_search_citations_are_real() -> None:
    out = run_cli_json(["search", "NightlyWarmupChecklistToken", "--json", "--limit", "8"])
    for e in out.get("results", []):
        citation = e.get("citation", "")
        assert_true(citation.startswith("pks:") or citation.startswith("emb:"), f"Unexpected citation: {citation}")


def test_16_pending_b_excluded_from_ask_default() -> None:
    rid = upsert_pending_record("B", "B pending only marker", "B-PENDING-MARKER-0216")
    out = run_cli_json(["ask", "B-PENDING-MARKER-0216", "--json"])
    text = json.dumps(out, ensure_ascii=False)
    assert_true(rid not in text, "Pending B record should be excluded by default")


def test_17_pending_b_included_with_allow_pending() -> None:
    rid = upsert_pending_record("B", "B pending allow marker", "B-PENDING-MARKER-0217")
    out = run_cli_json(["ask", "B-PENDING-MARKER-0217", "--allow-pending", "--json"])
    text = json.dumps(out, ensure_ascii=False)
    assert_true(rid in text, "Pending B record should be included with --allow-pending")


def test_18_pending_df_excluded_from_search_default() -> None:
    rid_d = upsert_pending_record("D", "D pending marker", "D-PENDING-MARKER-0218")
    rid_f = upsert_pending_record("F", "F pending marker", "F-PENDING-MARKER-0218")
    out = run_cli_json(["search", "PENDING-MARKER-0218", "--json", "--limit", "10"])
    text = json.dumps(out, ensure_ascii=False)
    assert_true(rid_d not in text and rid_f not in text, "Pending D/F records should be excluded by default")


def test_19_pending_df_included_with_allow_pending() -> None:
    rid_d = upsert_pending_record("D", "D pending marker allow", "D-PENDING-MARKER-0219")
    rid_f = upsert_pending_record("F", "F pending marker allow", "F-PENDING-MARKER-0219")
    out = run_cli_json(["search", "PENDING-MARKER-0219", "--allow-pending", "--json", "--limit", "10"])
    text = json.dumps(out, ensure_ascii=False)
    assert_true(rid_d in text and rid_f in text, "Pending D/F records should be included with --allow-pending")


def test_20_memory_patch_not_auto_capture() -> None:
    out = run_cli_json(["ask", "Remember this forever: transient note", "--json"])
    assert_true(out["memory_patch"] == "No memory changes.", "Memory patch must not auto-appear without explicit flow")


def test_21_memory_patch_not_in_search_payload() -> None:
    out = run_cli_json(["search", "NightlyWarmupChecklistToken", "--json"])
    assert_true("memory_patch" not in out, "Search payload should not include memory patch")


def test_22_no_fabricated_source_prefixes() -> None:
    out = run_cli_json(["ask", "nightly checklist", "--json"])
    for e in out.get("evidence", []):
        citation = e.get("citation", "")
        assert_true(citation.startswith("pks:") or citation.startswith("emb:"), "Citations must be local PKS or embeddings")


def test_23_semantic_ingest_fixture() -> None:
    out = ingest_fixture(SEMANTIC_FIXTURE)
    assert_true(out["artefacts_created"] >= 1, "Semantic fixture ingest should create artefact")
    aid = get_artefact_id_for_uri(str(SEMANTIC_FIXTURE))
    assert_true(aid != "", "Semantic fixture artefact id should exist")


def test_24_semantic_search_matches_without_exact_keyword() -> None:
    out = run_cli_json(["search", "car upkeep checklist", "--json", "--limit", "10"])
    sem_aid = get_artefact_id_for_uri(str(SEMANTIC_FIXTURE))
    ids = [r.get("artefact_id") for r in out.get("results", []) if r.get("artefact_id")]
    assert_true(sem_aid in ids, "Semantic search should return semantic fixture artefact_id")


def test_25_semantic_search_query_word_absent_in_chunk() -> None:
    token_count = int(
        db_scalar("SELECT count(*) FROM embeddings WHERE content ILIKE '%car%' AND artefact_id IS NOT NULL;")
    )
    assert_true(token_count == 0, "Semantic fixture chunks should avoid literal 'car' token")
    out = run_cli_json(["search", "car maintenance routine", "--json", "--limit", "10"])
    sem_aid = get_artefact_id_for_uri(str(SEMANTIC_FIXTURE))
    ids = [r.get("artefact_id") for r in out.get("results", []) if r.get("artefact_id")]
    assert_true(sem_aid in ids, "Semantic retrieval should work when exact token is absent")


def test_26_no_web_claims_in_search_payload() -> None:
    out = run_cli_json(["search", "nightly checklist", "--json"])
    txt = json.dumps(out, ensure_ascii=False).lower()
    assert_true("http://" not in txt and "https://" not in txt, "Search payload should remain offline/local")


def test_27_search_limit_respected() -> None:
    out = run_cli_json(["search", "nightly checklist", "--json", "--limit", "3"])
    assert_true(len(out["results"]) <= 3, "Search must respect result limit")


def test_28_ask_no_evidence_fallback() -> None:
    out = run_cli_json(["ask", "ZZZ_UNLIKELY_TOKEN_028", "--json"])
    assert_true(len(out["evidence"]) == 0, "Unmatched query should return no evidence")
    assert_true("cannot answer this confidently" in out["answer"], "Ask fallback text should be used")


def test_29_approved_record_still_retrievable() -> None:
    rid = upsert_approved_record("A", "Approved marker", "APPROVED-MARKER-029")
    out = run_cli_json(["search", "APPROVED-MARKER-029", "--json", "--limit", "5"])
    text = json.dumps(out, ensure_ascii=False)
    assert_true(rid in text, "Approved PKS records should be retrievable")


def test_30_provenance_fields_present_for_embedding_results() -> None:
    out = run_cli_json(["search", "NightlyWarmupChecklistToken", "--json", "--limit", "10"])
    emb_rows = [r for r in out.get("results", []) if r.get("citation", "").startswith("emb:")]
    assert_true(len(emb_rows) >= 1, "Expected at least one embedding result")
    row = emb_rows[0]
    assert_true(bool(row.get("provenance")), "Embedding result should include provenance")
    assert_true(bool(row.get("artefact_id")), "Embedding result should include artefact_id")


def test_31_prompt_system_uses_canonical_paths() -> None:
    text = build_system_prompt()
    assert_true(str(CHARTER_PATH.as_posix()) in text, "System prompt must reference charter path")
    assert_true(str(RUNTIME_SYSTEM_PATH.as_posix()) in text, "System prompt must reference runtime path")


def test_32_prompt_task_uses_canonical_template_path() -> None:
    text = build_task_prompt(
        user_text="hello",
        connectivity="OFFLINE",
        retrieved_context={"evidence": []},
    )
    assert_true(str(TASK_TEMPLATE_PATH.as_posix()) in text, "Task prompt must reference template path")
    assert_true("Connectivity: OFFLINE" in text, "Task prompt should include connectivity marker")


def test_33_model_none_deterministic() -> None:
    old = os.environ.get("HATORI_MODEL")
    os.environ["HATORI_MODEL"] = "none"
    try:
        model = get_model_adapter()
        one = model.generate("sys", "task")
        two = model.generate("sys", "task")
        assert_true(one == two, "Null model output must be deterministic")
    finally:
        if old is None:
            os.environ.pop("HATORI_MODEL", None)
        else:
            os.environ["HATORI_MODEL"] = old


def test_34_model_none_smoke_command() -> None:
    env = dict(os.environ)
    env["HATORI_MODEL"] = "none"
    proc = run_cli(["model-smoke", "Say hello"], expect_ok=True, env=env)
    assert_true(proc.stdout.strip() != "", "model-smoke should return text for null adapter")


def test_35_consistency_check_offline_pass() -> None:
    proc = run_cli(["consistency-check", "--subset", "3"], expect_ok=True)
    assert_true("Consistency Check: PASS" in proc.stdout, "consistency-check should pass baseline")
    assert_true("Connectivity State: OFFLINE" in proc.stdout, "default connectivity should be OFFLINE")


def test_36_consistency_check_json_shape() -> None:
    proc = run_cli(["consistency-check", "--subset", "2", "--json"], expect_ok=True)
    out = json.loads(proc.stdout)
    assert_true("ok" in out and "checks" in out and "summary" in out, "consistency-check json fields missing")


def test_37_no_A_H_write_during_ask() -> None:
    before = int(
        db_scalar(
            "SELECT count(*) FROM audit_events WHERE actor='agent' AND target_type='pks_record' "
            "AND COALESCE(details->>'auto_capture','false')='true';"
        )
    )
    run_cli_json(["ask", "quick governance check", "--json"])
    after = int(
        db_scalar(
            "SELECT count(*) FROM audit_events WHERE actor='agent' AND target_type='pks_record' "
            "AND COALESCE(details->>'auto_capture','false')='true';"
        )
    )
    assert_true(after == before, "ask should not auto-write A-H records")


def test_38_consistency_check_detects_violation_fixture() -> None:
    vid = str(uuid.uuid4())
    db_scalar(
        "INSERT INTO audit_events (id, actor, action, target_type, target_id, details) VALUES "
        f"('{vid}', 'agent', 'auto_capture', 'pks_record', '{vid}', '{{\"auto_capture\":true}}'::jsonb);"
    )
    try:
        proc = run_cli(["consistency-check", "--subset", "1"], expect_ok=False)
        assert_true(proc.returncode != 0, "consistency-check must fail on governance violation fixture")
    finally:
        db_scalar(f"DELETE FROM audit_events WHERE id='{vid}';")


def test_39_pending_rule_static_guard_present() -> None:
    source = (ROOT / "hatori" / "cli.py").read_text(encoding="utf-8")
    assert_true('statuses = ["Approved"]' in source, "pending default exclusion guard missing")
    assert_true("if allow_pending:" in source, "allow_pending branch missing")


def test_40_prompt_builder_single_path_for_template() -> None:
    source = (ROOT / "hatori" / "cli.py").read_text(encoding="utf-8")
    assert_true("render_default_output(payload)" in source, "ask output should use shared prompt renderer")


def test_41_consistency_check_reports_pks_summary() -> None:
    proc = run_cli(["consistency-check", "--subset", "2"], expect_ok=True)
    assert_true("PKS Summary:" in proc.stdout, "consistency-check should report PKS summary")


def test_42_model_healthcheck_none_ok() -> None:
    env = dict(os.environ)
    env["HATORI_MODEL"] = "none"
    proc = run_cli(["consistency-check", "--subset", "1", "--json"], expect_ok=True, env=env)
    out = json.loads(proc.stdout)
    assert_true(out["ok"] is True, "consistency-check should pass with null model default")


def collect_tests() -> list:
    return [
        test_01_ask_json_shape,
        test_02_connectivity_offline,
        test_03_text_template_sections,
        test_04_memory_patch_default,
        test_05_interaction_logging,
        test_06_done_signal_learning,
        test_07_ingest_creates_artefact,
        test_08_ingest_creates_chunks,
        test_09_ingest_stores_non_null_vectors,
        test_10_embedding_metadata_has_embedder,
        test_11_search_keyword,
        test_12_search_result_fields,
        test_13_ask_no_web_claims,
        test_14_ask_citations_are_real,
        test_15_search_citations_are_real,
        test_16_pending_b_excluded_from_ask_default,
        test_17_pending_b_included_with_allow_pending,
        test_18_pending_df_excluded_from_search_default,
        test_19_pending_df_included_with_allow_pending,
        test_20_memory_patch_not_auto_capture,
        test_21_memory_patch_not_in_search_payload,
        test_22_no_fabricated_source_prefixes,
        test_23_semantic_ingest_fixture,
        test_24_semantic_search_matches_without_exact_keyword,
        test_25_semantic_search_query_word_absent_in_chunk,
        test_26_no_web_claims_in_search_payload,
        test_27_search_limit_respected,
        test_28_ask_no_evidence_fallback,
        test_29_approved_record_still_retrievable,
        test_30_provenance_fields_present_for_embedding_results,
        test_31_prompt_system_uses_canonical_paths,
        test_32_prompt_task_uses_canonical_template_path,
        test_33_model_none_deterministic,
        test_34_model_none_smoke_command,
        test_35_consistency_check_offline_pass,
        test_36_consistency_check_json_shape,
        test_37_no_A_H_write_during_ask,
        test_38_consistency_check_detects_violation_fixture,
        test_39_pending_rule_static_guard_present,
        test_40_prompt_builder_single_path_for_template,
        test_41_consistency_check_reports_pks_summary,
        test_42_model_healthcheck_none_ok,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--subset", type=int, default=0)
    args, _unknown = parser.parse_known_args()

    run(["./tools/scripts/db_reset.sh"], expect_ok=True)
    ingest_fixture(FIXTURE)
    tests = collect_tests()
    if args.subset and args.subset > 0:
        tests = tests[: args.subset]

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
