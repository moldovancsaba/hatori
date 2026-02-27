import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hatori.model import get_model_adapter
from hatori.model_gateway import ModelGateway
from hatori.prompts import CHARTER_PATH
from hatori.prompts import RUNTIME_SYSTEM_PATH
from hatori.prompts import TASK_TEMPLATE_PATH
from hatori.prompts import build_system_prompt
from hatori.prompts import build_task_prompt
try:
    from fastapi.testclient import TestClient
    from api.app import app as api_app
    from ui.app import app as ui_app
except Exception as exc:
    raise RuntimeError(
        "UI test dependencies unavailable. Install ui/requirements.txt before running tests. "
        f"Import error: {exc}"
    ) from exc

FIXTURE = ROOT / "tests" / "golden" / "fixtures" / "offline_playbook.txt"
SEMANTIC_FIXTURE = ROOT / "tests" / "golden" / "fixtures" / "semantic_garage.txt"
UPLOAD_FIXTURE = ROOT / "tests" / "golden" / "fixtures" / "upload_note.txt"


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


class FakeBackend:
    def __init__(self, name: str, available: bool = True, output: str = "ok", error: str = "") -> None:
        self.name = name
        self._available = available
        self._output = output
        self._error = error

    def healthcheck(self, timeout_s: float | None = None):
        del timeout_s
        return self._available, ("" if self._available else (self._error or "unavailable"))

    def generate(self, prompt: str, timeout_s: float | None = None):
        del prompt, timeout_s
        if self._error:
            raise RuntimeError(self._error)
        return self._output


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


def ui_client():
    return TestClient(ui_app)


def api_client():
    return TestClient(api_app)


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


def test_34b_model_ollama_adapter_selectable() -> None:
    old_model = os.environ.get("HATORI_MODEL")
    old_name = os.environ.get("HATORI_OLLAMA_MODEL")
    os.environ["HATORI_MODEL"] = "ollama"
    os.environ["HATORI_OLLAMA_MODEL"] = "llama3.2:3b"
    try:
        model = get_model_adapter()
        assert_true(model.name == "ollama", "HATORI_MODEL=ollama should select OllamaAdapter")
    finally:
        if old_model is None:
            os.environ.pop("HATORI_MODEL", None)
        else:
            os.environ["HATORI_MODEL"] = old_model
        if old_name is None:
            os.environ.pop("HATORI_OLLAMA_MODEL", None)
        else:
            os.environ["HATORI_OLLAMA_MODEL"] = old_name


def test_34c_gateway_prefers_mlx_when_available() -> None:
    gw = ModelGateway(
        backends={
            "mlx": FakeBackend("mlx", available=True, output="Szia, ez MLX válasz."),
            "ollama": FakeBackend("ollama", available=True, output="Szia, ez Ollama válasz."),
        }
    )
    out = gw.generate("Respond in Hungarian.")
    assert_true(out.backend_used == "mlx", "gateway should prefer mlx when available")
    assert_true(out.backend_fallback_used is False, "gateway should not mark fallback when mlx succeeds")
    assert_true("MLX" in out.text or "mlx" in out.text.lower(), "mlx output should be returned")


def test_34d_gateway_fallbacks_to_ollama_on_mlx_failure() -> None:
    gw = ModelGateway(
        backends={
            "mlx": FakeBackend("mlx", available=True, output="", error="mlx failed"),
            "ollama": FakeBackend("ollama", available=True, output="Ollama fallback output."),
        }
    )
    out = gw.generate("Respond in English.")
    assert_true(out.backend_used == "ollama", "gateway should fallback to ollama when mlx fails")
    assert_true(out.backend_fallback_used is True, "fallback flag should be true after mlx failure")
    assert_true("fallback" in out.text.lower(), "ollama fallback output should be returned")


def test_34e_gateway_returns_clean_error_when_all_fail() -> None:
    gw = ModelGateway(
        backends={
            "mlx": FakeBackend("mlx", available=False, error="mlx unavailable"),
            "ollama": FakeBackend("ollama", available=False, error="ollama unavailable"),
        }
    )
    out = gw.generate("Respond in Hungarian.")
    lowered = out.text.lower()
    assert_true(out.backend_used == "none", "all-fail should use backend none")
    assert_true("nem tudok most válaszolni" in lowered, "all-fail should return clean localized Hungarian message")
    assert_true("traceback" not in lowered and "runtimeerror" not in lowered, "all-fail user text must not leak internal errors")


def test_34f_gateway_output_still_passes_leakage_validator() -> None:
    gw = ModelGateway(
        backends={
            "mlx": FakeBackend("mlx", available=True, output="User request: leak this\nemb:test"),
            "ollama": FakeBackend("ollama", available=True, output="Tiszta válasz belső marker nélkül."),
        }
    )
    out = gw.generate("Respond in Hungarian.")
    lowered = out.text.lower()
    assert_true(out.backend_used == "ollama", "unsafe mlx output should trigger fallback backend")
    assert_true("user request:" not in lowered and "emb:" not in lowered, "gateway output must pass leakage validator")


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


def test_43_chat_get_returns_200() -> None:
    client = ui_client()
    resp = client.get("/chat")
    assert_true(resp.status_code == 200, "GET /chat should return 200")
    assert_true("Chat" in resp.text, "/chat page should render chat content")

    old_order = os.environ.get("HATORI_GENERATOR_ORDER")
    old_mlx = os.environ.get("HATORI_MLX_MODEL")
    old_ollama_url = os.environ.get("HATORI_OLLAMA_URL")
    os.environ["HATORI_GENERATOR_ORDER"] = "mlx,ollama"
    os.environ.pop("HATORI_MLX_MODEL", None)
    os.environ["HATORI_OLLAMA_URL"] = "http://127.0.0.1:1"
    try:
        chat_id = "golden-chat-43-misconfig"
        send = client.post("/chat/send", data={"chat_id": chat_id, "message": "check misconfig handling"})
        assert_true(send.status_code in {200, 303}, "chat send should not crash when local generators are unavailable")
        assistant_text = db_scalar(
            "SELECT content FROM interaction_events "
            f"WHERE role='assistant' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
            "ORDER BY occurred_at DESC LIMIT 1;"
        ).lower()
        assert_true("helyi modell" in assistant_text or "local model" in assistant_text, "gateway all-fail should return clear local-model error text")
    finally:
        if old_order is None:
            os.environ.pop("HATORI_GENERATOR_ORDER", None)
        else:
            os.environ["HATORI_GENERATOR_ORDER"] = old_order
        if old_mlx is None:
            os.environ.pop("HATORI_MLX_MODEL", None)
        else:
            os.environ["HATORI_MLX_MODEL"] = old_mlx
        if old_ollama_url is None:
            os.environ.pop("HATORI_OLLAMA_URL", None)
        else:
            os.environ["HATORI_OLLAMA_URL"] = old_ollama_url


def test_44_chat_send_creates_user_and_assistant_rows() -> None:
    client = ui_client()
    chat_id = "golden-chat-44"
    before = int(
        db_scalar(
            "SELECT count(*) FROM interaction_events "
            f"WHERE COALESCE(metadata->>'chat_id','')='{chat_id}';"
        )
    )
    resp = client.post("/chat/send", data={"chat_id": chat_id, "message": "hello from chat 44"})
    assert_true(resp.status_code in {200, 303}, "POST /chat/send should succeed")
    after = int(
        db_scalar(
            "SELECT count(*) FROM interaction_events "
            f"WHERE COALESCE(metadata->>'chat_id','')='{chat_id}';"
        )
    )
    assert_true(after == before + 2, "chat send should create user+assistant interaction rows")
    assistant_text = db_scalar(
        "SELECT content FROM interaction_events "
        f"WHERE role='assistant' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    lower = assistant_text.lower()
    assert_true("1) connectivity state" not in lower and "2) answer / recommendation" not in lower, "assistant output should be plain human message without template headers")
    assert_true("placeholder" not in lower and "dummy" not in lower and "tbd" not in lower, "assistant output must be real text")


def test_45_chat_send_metadata_linking() -> None:
    chat_id = "golden-chat-45"
    run_cli_json(["ask", "seed baseline for 45", "--json"])
    client = ui_client()
    client.post("/chat/send", data={"chat_id": chat_id, "message": "link check"})
    user_id = db_scalar(
        "SELECT id FROM interaction_events "
        f"WHERE role='user' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    assistant_related = db_scalar(
        "SELECT metadata->>'related_user_interaction_id' FROM interaction_events "
        f"WHERE role='assistant' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    assistant_language = db_scalar(
        "SELECT COALESCE(metadata->>'language','') FROM interaction_events "
        f"WHERE role='assistant' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    assert_true(user_id != "" and assistant_related == user_id, "assistant message metadata should link to user interaction")
    assert_true(assistant_language == "en", "assistant metadata language should follow user message language")


def test_46_feedback_up_creates_positive_learning() -> None:
    client = ui_client()
    chat_id = "golden-chat-46"
    client.post("/chat/send", data={"chat_id": chat_id, "message": "feedback up"})
    assistant_id = db_scalar(
        "SELECT id FROM interaction_events "
        f"WHERE role='assistant' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    before = int(db_scalar("SELECT count(*) FROM learning_events WHERE kind='PositiveFeedback';"))
    resp = client.post(
        "/chat/feedback",
        data={"chat_id": chat_id, "interaction_id": assistant_id, "vote": "up", "category": "", "comment": ""},
    )
    assert_true(resp.status_code in {200, 303}, "up feedback should succeed")
    after = int(db_scalar("SELECT count(*) FROM learning_events WHERE kind='PositiveFeedback';"))
    assert_true(after == before + 1, "up feedback should create PositiveFeedback row")
    linked = db_scalar(
        "SELECT count(*) FROM learning_events "
        f"WHERE kind='PositiveFeedback' AND related_interaction_id='{assistant_id}';"
    )
    assert_true(int(linked) >= 1, "PositiveFeedback should link to assistant interaction id")


def test_47_feedback_down_requires_context() -> None:
    client = ui_client()
    chat_id = "golden-chat-47"
    client.post("/chat/send", data={"chat_id": chat_id, "message": "feedback down validation"})
    assistant_id = db_scalar(
        "SELECT id FROM interaction_events "
        f"WHERE role='assistant' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    resp = client.post(
        "/chat/feedback",
        data={"chat_id": chat_id, "interaction_id": assistant_id, "vote": "down", "category": "", "comment": ""},
    )
    assert_true(resp.status_code == 400, "down feedback without category/comment should fail")


def test_48_feedback_down_creates_negative_learning() -> None:
    client = ui_client()
    chat_id = "golden-chat-48"
    client.post("/chat/send", data={"chat_id": chat_id, "message": "feedback down create"})
    assistant_id = db_scalar(
        "SELECT id FROM interaction_events "
        f"WHERE role='assistant' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    before = int(db_scalar("SELECT count(*) FROM learning_events WHERE kind='NegativeFeedback';"))
    resp = client.post(
        "/chat/feedback",
        data={
            "chat_id": chat_id,
            "interaction_id": assistant_id,
            "vote": "down",
            "category": "accuracy",
            "comment": "wrong response",
        },
    )
    assert_true(resp.status_code in {200, 303}, "down feedback with category/comment should succeed")
    after = int(db_scalar("SELECT count(*) FROM learning_events WHERE kind='NegativeFeedback';"))
    assert_true(after == before + 1, "down feedback should create NegativeFeedback row")


def test_49_upload_txt_creates_artefact_and_embeddings() -> None:
    client = ui_client()
    before_art = int(db_scalar("SELECT count(*) FROM artefacts;"))
    before_emb = int(db_scalar("SELECT count(*) FROM embeddings;"))
    with UPLOAD_FIXTURE.open("rb") as fh:
        resp = client.post("/upload", files={"file": (UPLOAD_FIXTURE.name, fh, "text/plain")})
    assert_true(resp.status_code == 200, "POST /upload should return success page")
    after_art = int(db_scalar("SELECT count(*) FROM artefacts;"))
    after_emb = int(db_scalar("SELECT count(*) FROM embeddings;"))
    assert_true(after_art == before_art + 1, "upload should create one artefact row")
    assert_true(after_emb > before_emb, "upload .txt should create embedding chunks")


def test_50_upload_content_searchable_in_ui() -> None:
    out = run_cli_json(["search", "UploadFixtureToken-0401", "--json", "--limit", "5"])
    assert_true(len(out.get("results", [])) >= 1, "uploaded txt token should be searchable")
    client = ui_client()
    resp = client.get("/search", params={"query": "UploadFixtureToken-0401", "limit": "5"})
    assert_true(resp.status_code == 200, "GET /search should return 200")
    assert_true("artefact_id=" in resp.text, "/search UI should show artefact provenance")


def _daily_planning_chat_output(chat_id: str, message: str, model_mode: str = "none") -> str:
    old_model = os.environ.get("HATORI_MODEL")
    os.environ["HATORI_MODEL"] = model_mode
    try:
        client = ui_client()
        resp = client.post("/chat/send", data={"chat_id": chat_id, "message": message})
        assert_true(resp.status_code in {200, 303}, "chat send should succeed for planning request")
    finally:
        if old_model is None:
            os.environ.pop("HATORI_MODEL", None)
        else:
            os.environ["HATORI_MODEL"] = old_model

    assistant_text = db_scalar(
        "SELECT content FROM interaction_events "
        f"WHERE role='assistant' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    assert_true(assistant_text != "", "assistant planning response should be non-empty")
    return assistant_text


def _assert_human_output(text: str) -> None:
    lowered = text.lower()
    assert_true("1) kapcsolati állapot" not in lowered and "1) connectivity state" not in lowered, "template headers must not appear in user-visible output")
    assert_true("memory patch" not in lowered and "tanulási napló" not in lowered, "internal scaffolding must not appear in user-visible output")
    assert_true(len(text.strip()) >= 24, "assistant output must be non-empty and human-readable")


def _extract_section(text: str, section_number: int, next_section_number: int) -> str:
    start_re = re.compile(rf"(?m)^{section_number}\)\s+.+$")
    end_re = re.compile(rf"(?m)^{next_section_number}\)\s+.+$")
    start_match = start_re.search(text)
    if start_match is None:
        return text
    end_match = end_re.search(text, start_match.end())
    if end_match is None:
        return text[start_match.end():]
    return text[start_match.end():end_match.start()]


PLANNING_TODAY_HU_MESSAGE = (
    "Ma kérlek készíts nekem egy rövid, pragmatikus napi tervet. "
    "Keretek: OFFLINE módban vagyunk (ne hivatkozz webre). "
    "Nincs naptáradatod és nem adok meg fix meetingeket. "
    "Legyen 5–8 konkrét teendő, priorizálva. "
    "Írd le a kritikus feltételezéseket. "
    "Ne írj memóriába semmit automatikusan. "
    "A válasz legyen a standard sablon szerint."
)


def test_60_planning_today_hu_language_mirror() -> None:
    chat_id = "golden-plan-60"
    out = _daily_planning_chat_output(chat_id, PLANNING_TODAY_HU_MESSAGE)
    _assert_human_output(out)
    lowered = out.lower()
    hu_markers = ["ma", "feladat", "feltetelezes", "feltételezés", "kovetkezo", "következő", "lepes", "lépések"]
    marker_hits = sum(1 for m in hu_markers if m in lowered)
    assert_true(marker_hits >= 3, "Planning response should be predominantly Hungarian")
    assert_true("offline deterministic response" not in lowered, "Planning response should not be an English placeholder")
    assert_true("kapcsolati állapot: offline" not in lowered, "plain planning output must not include template connectivity headers")


def test_61_planning_today_includes_default_template_sections() -> None:
    chat_id = "golden-plan-61"
    out = _daily_planning_chat_output(chat_id, PLANNING_TODAY_HU_MESSAGE)
    _assert_human_output(out)
    assert_true("következő lépések" in out.lower() or "next actions" in out.lower(), "planning output should include a natural next-actions block")


def test_62_planning_today_assumptions_present_when_calendar_unknown() -> None:
    chat_id = "golden-plan-62"
    out = _daily_planning_chat_output(chat_id, PLANNING_TODAY_HU_MESSAGE)
    assumptions = _extract_section(out, 4, 5).lower()
    assert_true(
        ("nincs atadott naptar" in assumptions) or ("nincs átadott naptár" in assumptions) or ("no explicit calendar" in assumptions),
        "Assumptions should mention missing calendar input",
    )
    assert_true("meeting" in assumptions, "Assumptions should mention missing meetings")


def test_63_planning_today_next_actions_count_and_priority() -> None:
    chat_id = "golden-plan-63"
    out = _daily_planning_chat_output(chat_id, PLANNING_TODAY_HU_MESSAGE)
    next_actions = _extract_section(out, 5, 6)
    checklist_count = next_actions.count("[ ]")
    assert_true(5 <= checklist_count <= 8, "Today planning should contain 5-8 concrete next-action items")
    lowered = next_actions.lower()
    assert_true("p0" in lowered or "p1" in lowered, "Today planning should include explicit prioritization labels")


def test_64_planning_today_no_web_claims_offline() -> None:
    chat_id = "golden-plan-64"
    out = _daily_planning_chat_output(chat_id, PLANNING_TODAY_HU_MESSAGE)
    lowered = out.lower()
    assert_true("http://" not in lowered and "https://" not in lowered, "Planning output must not include web URLs")
    assert_true("verified" not in lowered, "Planning output must not claim verification")
    assert_true("source:" not in lowered, "Planning output must not imply external web sources")


def test_65_planning_today_no_memory_patch_by_default() -> None:
    chat_id = "golden-plan-65"
    before_pks_ah = int(db_scalar("SELECT count(*) FROM pks_records WHERE module IN ('A','B','C','D','E','F','G','H');"))
    out = _daily_planning_chat_output(chat_id, PLANNING_TODAY_HU_MESSAGE)
    out_lower = out.lower()
    assert_true("nincs memória módosítás" not in out_lower and "no memory changes" not in out_lower, "plain output should not include memory-patch template text")
    after_pks_ah = int(db_scalar("SELECT count(*) FROM pks_records WHERE module IN ('A','B','C','D','E','F','G','H');"))
    assert_true(after_pks_ah == before_pks_ah, "Planning response must not auto-write PKS A-H")


def test_66_planning_today_learning_log_default() -> None:
    chat_id = "golden-plan-66"
    before = int(db_scalar("SELECT count(*) FROM learning_events;"))
    out = _daily_planning_chat_output(chat_id, PLANNING_TODAY_HU_MESSAGE)
    after = int(db_scalar("SELECT count(*) FROM learning_events;"))
    assert_true(after == before, "Planning response path should not auto-log learning events without feedback")
    assert_true("tanulási napló" not in out.lower() and "learning log" not in out.lower(), "plain output should not contain learning-log section scaffolding")


def test_67_planning_today_no_fabricated_commitments() -> None:
    chat_id = "golden-plan-67"
    out = _daily_planning_chat_output(chat_id, PLANNING_TODAY_HU_MESSAGE, model_mode="none")
    _assert_human_output(out)
    lowered = out.lower()
    answer = _extract_section(out, 2, 3).lower()
    fabricated_markers = [
        "meeting at ",
        "stakeholder",
        "deadline:",
        "koztelezo meeting",
        "egyeztetes 10:00",
        "hatarido:",
    ]
    assert_true(not any(m in answer for m in fabricated_markers), "Planning answer must not invent meetings/stakeholders/deadlines")
    assert_true(
        ("feltetelezes" in lowered) or ("feltételezés" in lowered) or ("assumption" in lowered),
        "Unknown commitments should be framed as assumptions",
    )
    assert_true("placeholder" not in lowered and "dummy" not in lowered and "tbd" not in lowered, "Planning output must not be placeholder text")


def _chat_send_and_get_output(chat_id: str, message: str, model_mode: str = "none") -> str:
    old_model = os.environ.get("HATORI_MODEL")
    os.environ["HATORI_MODEL"] = model_mode
    try:
        client = ui_client()
        resp = client.post("/chat/send", data={"chat_id": chat_id, "message": message})
        assert_true(resp.status_code in {200, 303}, "chat send should succeed")
    finally:
        if old_model is None:
            os.environ.pop("HATORI_MODEL", None)
        else:
            os.environ["HATORI_MODEL"] = old_model
    return db_scalar(
        "SELECT content FROM interaction_events "
        f"WHERE role='assistant' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )


def test_68_chat_no_prompt_leakage_markers() -> None:
    out = _chat_send_and_get_output("golden-chat-68", "Please provide a concise plan.")
    lowered = out.lower()
    forbidden = ["task prompt", "retrieved pks", "required behaviour", "active project", "```"]
    assert_true(not any(x in lowered for x in forbidden), "assistant output must not leak internal scaffolding markers")


def test_69_chat_hungarian_language_mirror() -> None:
    out = _chat_send_and_get_output("golden-chat-69", "Szia! Szükségem lesz a segítségedre")
    lowered = out.lower()
    assert_true("2) válasz / javaslat" not in lowered and "2) answer / recommendation" not in lowered, "Hungarian response must avoid template labels")
    assert_true("please" not in lowered and "answer / recommendation" not in lowered, "Hungarian response should avoid English template/fallback text")
    assert_true("nem tudok most válaszolni" in lowered or any(ch in lowered for ch in ["kérlek", "próbáld", "szia", "segíts", "segit"]), "Hungarian response should mirror language naturally")
    assert_true("continue the chat with a follow-up" not in lowered, "Hungarian response must not include English fallback lines")


def test_70_chat_template_sections_present() -> None:
    out = _chat_send_and_get_output("golden-chat-70", "Please give a short practical plan.")
    lowered = out.lower()
    assert_true("1) connectivity state" not in lowered and "2) answer / recommendation" not in lowered, "chat output should not use section template")
    assert_true(len(out.strip()) > 24, "chat output should be non-empty human text")


def test_71_chat_no_placeholder_markers() -> None:
    out = _chat_send_and_get_output("golden-chat-71", "Give me a useful one-paragraph recommendation.")
    lowered = out.lower()
    assert_true("[null-adapter:" not in lowered, "assistant output must not contain null-adapter placeholder marker")


def test_72_chat_decline_feedback_logging_unchanged() -> None:
    client = ui_client()
    chat_id = "golden-chat-72"
    client.post("/chat/send", data={"chat_id": chat_id, "message": "feedback path consistency"})
    assistant_id = db_scalar(
        "SELECT id FROM interaction_events "
        f"WHERE role='assistant' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    before = int(db_scalar("SELECT count(*) FROM learning_events WHERE kind='NegativeFeedback';"))
    resp = client.post(
        "/chat/feedback",
        data={"chat_id": chat_id, "interaction_id": assistant_id, "vote": "down", "category": "format", "comment": "too long"},
    )
    assert_true(resp.status_code in {200, 303}, "decline feedback should still succeed")
    after = int(db_scalar("SELECT count(*) FROM learning_events WHERE kind='NegativeFeedback';"))
    assert_true(after == before + 1, "decline feedback should still write exactly one NegativeFeedback event")


def test_73_chat_sanitizer_repair_path() -> None:
    out = _chat_send_and_get_output("golden-chat-73", "LEAKAGE_FIXTURE please help me with a clean answer.", model_mode="none")
    lowered = out.lower()
    forbidden = [
        "task prompt",
        "retrieved pks",
        "required behaviour",
        "active project",
        "connectivity:",
        "time:",
        "```",
    ]
    assert_true(not any(x in lowered for x in forbidden), "sanitizer/repair path must remove leaked scaffolding")
    assert_true(len(out.strip()) >= 12, "sanitizer repair path should still produce non-empty user-visible output")


def test_74_chat_ollama_down_returns_clean_error_not_stub() -> None:
    old_model = os.environ.get("HATORI_MODEL")
    old_url = os.environ.get("HATORI_OLLAMA_URL")
    os.environ.pop("HATORI_MODEL", None)
    os.environ["HATORI_OLLAMA_URL"] = "http://127.0.0.1:1"
    try:
        out = _chat_send_and_get_output("golden-chat-74", "Szia! Kérlek adj rövid segítséget.", model_mode="")
    finally:
        if old_model is None:
            os.environ.pop("HATORI_MODEL", None)
        else:
            os.environ["HATORI_MODEL"] = old_model
        if old_url is None:
            os.environ.pop("HATORI_OLLAMA_URL", None)
        else:
            os.environ["HATORI_OLLAMA_URL"] = old_url
    lowered = out.lower()
    assert_true(
        ("ollama" in lowered and "mlx" in lowered and "helyi modell" in lowered)
        or ("local model is unavailable" in lowered),
        "ollama-down path should show clean local-model startup guidance",
    )
    assert_true("[null-adapter:" not in lowered and "nulladapter" not in lowered and "fingerprint" not in lowered, "ollama-down path must not produce stub output")


def test_75_chat_new_chat_id_default_no_seed_messages() -> None:
    client = ui_client()
    old_chat = "golden-chat-old-75"
    old_marker = "SEED_DEBUG_75_OLD"
    client.post("/chat/send", data={"chat_id": old_chat, "message": old_marker})

    resp = client.get("/chat", follow_redirects=False)
    assert_true(resp.status_code == 303, "GET /chat without chat_id should redirect to a new chat_id")
    location = resp.headers.get("location", "")
    assert_true(location.startswith("/chat?chat_id="), "redirect should include generated chat_id")
    new_chat_id = location.split("chat_id=", 1)[1].split("&", 1)[0]
    assert_true(new_chat_id != "" and new_chat_id != old_chat, "new default chat_id should be unique")

    page = client.get(location)
    assert_true(page.status_code == 200, "redirected chat page should render")
    main_section = page.text.split("<section class='chat-main'>", 1)[-1]
    assert_true(old_marker not in main_section, "new chat main timeline must not show messages from older chat threads")


def test_76_chat_filters_by_chat_id_only() -> None:
    client = ui_client()
    chat_a = "golden-chat-a-76"
    chat_b = "golden-chat-b-76"
    marker_a = "THREAD_ONLY_A_76"
    marker_b = "THREAD_ONLY_B_76"
    client.post("/chat/send", data={"chat_id": chat_a, "message": marker_a})
    client.post("/chat/send", data={"chat_id": chat_b, "message": marker_b})

    page_a = client.get("/chat", params={"chat_id": chat_a})
    assert_true(page_a.status_code == 200, "chat A page should render")
    main_a = page_a.text.split("<section class='chat-main'>", 1)[-1]
    assert_true(marker_a in main_a, "chat A page should include chat A messages")
    assert_true(marker_b not in main_a, "chat A main timeline must exclude chat B messages")

    page_b = client.get("/chat", params={"chat_id": chat_b})
    assert_true(page_b.status_code == 200, "chat B page should render")
    main_b = page_b.text.split("<section class='chat-main'>", 1)[-1]
    assert_true(marker_b in main_b, "chat B page should include chat B messages")
    assert_true(marker_a not in main_b, "chat B main timeline must exclude chat A messages")


def test_77_chat_enter_send_shift_enter_newline() -> None:
    client = ui_client()
    chat_id = "golden-chat-77"
    multiline = "Első sor\nMásodik sor"
    resp = client.post("/chat/send", data={"chat_id": chat_id, "message": multiline})
    assert_true(resp.status_code in {200, 303}, "multiline chat send should succeed")

    stored = db_scalar(
        "SELECT content FROM interaction_events "
        f"WHERE role='user' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    assert_true(stored == multiline, "stored user interaction must preserve newline content")

    page = client.get("/chat", params={"chat_id": chat_id})
    assert_true(page.status_code == 200, "chat page should render after multiline send")
    assert_true("Első sor" in page.text and "Második sor" in page.text, "multiline message should render in chat timeline")


def test_78_chat_no_scaffolding_markers() -> None:
    out = _chat_send_and_get_output("golden-chat-78", "Please give me a practical recommendation.")
    lowered = out.lower()
    forbidden = ["task prompt", "retrieved pks", "required behaviour", "active project", "```"]
    assert_true(not any(m in lowered for m in forbidden), "chat output must not expose prompt scaffolding markers")


def test_79_chat_language_mirror_hu_no_english_leak() -> None:
    out = _chat_send_and_get_output("golden-chat-79", "Szia! Kérlek adj rövid napi tervet.")
    lowered = out.lower()
    assert_true("2) válasz / javaslat" not in lowered and "2) answer / recommendation" not in lowered, "Hungarian response must avoid template labels")
    assert_true("következő lépések" in lowered or "p0 [ ]" in lowered, "planning response should include Hungarian action content")
    assert_true("next actions" not in lowered, "Hungarian response must not leak English section titles")


def test_80_chat_uses_history_for_followup() -> None:
    client = ui_client()
    chat_id = "golden-chat-80"
    first = client.post("/chat/send", data={"chat_id": chat_id, "message": "A projekt neve Nebula."})
    assert_true(first.status_code in {200, 303}, "first turn should succeed")
    second = client.post("/chat/send", data={"chat_id": chat_id, "message": "Mi a projekt neve?"})
    assert_true(second.status_code in {200, 303}, "follow-up turn should succeed")

    out = db_scalar(
        "SELECT content FROM interaction_events "
        f"WHERE role='assistant' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    assert_true("Nebula" in out, "follow-up answer should use same-thread history context")


def test_81_chat_greeting_only_asks_clarifying_question_hu() -> None:
    out = _chat_send_and_get_output("golden-chat-81", "Szia, szép reggelt")
    lowered = out.lower()
    assert_true("2) válasz / javaslat" not in lowered, "Hungarian output should be plain answer")
    answer_section = out
    assert_true(answer_section.count("?") == 1, "Greeting-only reply should ask exactly one clarifying question")
    assert_true("miben segíthetek pontosan ma" in answer_section.lower(), "Greeting-only HU reply should ask a clear clarifying question")
    assert_true("orvosi" not in lowered and "medical" not in lowered, "Greeting-only reply must not invent unrelated topics")
    forbidden = ["follow charter", "követelmények", "required behaviour", "retrieved pks"]
    assert_true(not any(m in lowered for m in forbidden), "Greeting-only reply must not leak policy/procedure scaffolding")


def test_82_chat_preview_does_not_show_template_headers() -> None:
    client = ui_client()
    chat_view = "golden-chat-82-view"
    chat_preview = "golden-chat-82-preview"
    preview_message = "SIDEBAR_PREVIEW_82 Kérlek ezt mutasd előnézetben."
    client.post("/chat/send", data={"chat_id": chat_view, "message": "nézet chat"})
    client.post("/chat/send", data={"chat_id": chat_preview, "message": preview_message})

    page = client.get("/chat", params={"chat_id": chat_view})
    assert_true(page.status_code == 200, "chat page should render for preview test")
    idx = page.text.find("SIDEBAR_PREVIEW_82")
    assert_true(idx >= 0, "sidebar should include user preview snippet")
    window = page.text[max(0, idx - 180): idx + 220]
    assert_true("1) Kapcsolati állapot" not in window and "Connectivity State" not in window, "sidebar preview must not show template section headers")


def test_83_chat_no_policy_dump_markers() -> None:
    out = _chat_send_and_get_output("golden-chat-83", "Szia, szép reggelt")
    lowered = out.lower()
    forbidden = [
        "follow charter",
        "követelmények",
        "kovetelmenyek",
        "required behaviour",
        "retrieved pks",
        "active project",
        "memory patch:",
    ]
    assert_true(not any(m in lowered for m in forbidden), "assistant output must not contain internal policy/procedure dump markers")


def test_84_utf8_roundtrip_hu_message() -> None:
    client = ui_client()
    chat_id = "golden-chat-84"
    original = "Kérlek segíts, őűáéíóöü"
    resp = client.post("/chat/send", data={"chat_id": chat_id, "message": original})
    assert_true(resp.status_code in {200, 303}, "UTF-8 send should succeed")
    stored = db_scalar(
        "SELECT content FROM interaction_events "
        f"WHERE role='user' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    assert_true(stored == original, f"UTF-8 roundtrip mismatch: expected={original!r} got={stored!r}")
    page = client.get("/chat", params={"chat_id": chat_id})
    assert_true(page.status_code == 200, "chat page should render for UTF-8 verification")
    assert_true(original in page.text, "Rendered HTML should preserve Hungarian accents without mojibake")


def test_85_chat_no_uuid_or_emb_ids_in_output() -> None:
    out = _chat_send_and_get_output("golden-chat-85", PLANNING_TODAY_HU_MESSAGE)
    lowered = out.lower()
    uuid_any_re = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)
    assert_true(uuid_any_re.search(lowered) is None, "assistant output must not contain UUIDs")
    assert_true("emb:" not in lowered and "artefact_id" not in lowered, "assistant output must not contain emb ids or artefact_id markers")


def test_86_chat_no_user_request_echo() -> None:
    out = _chat_send_and_get_output("golden-chat-86", "Szia, készíts rövid napi tervet.")
    lowered = out.lower()
    assert_true("user request:" not in lowered, "assistant output must not echo 'User request:'")


def test_87_chat_sources_are_human_readable_only() -> None:
    out = _chat_send_and_get_output("golden-chat-87", "NightlyWarmupChecklistToken lépései röviden?")
    lowered = out.lower()
    assert_true("emb:" not in lowered and "artefact_id" not in lowered, "user-visible output must not contain internal ids")
    assert_true("evidence & sources" not in lowered and "bizonyítékok és források" not in lowered, "plain output must not expose template evidence section")


def test_88_chat_repair_triggers_on_uuid_leak() -> None:
    before = int(db_scalar("SELECT count(*) FROM learning_events WHERE kind='NegativeFeedback';"))
    out = _chat_send_and_get_output("golden-chat-88", "UUID_LEAK_FIXTURE")
    after = int(db_scalar("SELECT count(*) FROM learning_events WHERE kind='NegativeFeedback';"))
    lowered = out.lower()
    assert_true(after >= before, "uuid leakage path should not reduce negative feedback rows")
    assert_true("user request:" not in lowered and "emb:" not in lowered, "final user-visible output must be clean after repair/fail-safe")
    assert_true("123e4567-e89b-12d3-a456-426614174000" not in lowered, "final output must not contain leaked UUID")


def test_89_planning_today_returns_real_plan_hu() -> None:
    out = _daily_planning_chat_output("golden-plan-89", PLANNING_TODAY_HU_MESSAGE)
    answer = _extract_section(out, 2, 3).lower()
    next_actions = _extract_section(out, 5, 6)
    assert_true("napi terv" in answer or "mai" in answer or "terv" in answer, "planning answer should contain real planning content")
    checklist_count = next_actions.count("[ ]")
    assert_true(5 <= checklist_count <= 8, "planning next actions should contain 5-8 checklist items")


def test_90_planning_today_never_refusal_fallback() -> None:
    out = _daily_planning_chat_output("golden-plan-90", PLANNING_TODAY_HU_MESSAGE)
    lowered = out.lower()
    assert_true("nem tudok biztonságos" not in lowered, "planning must not hit refusal fallback")
    assert_true("próbáld újra rövidebb" not in lowered and "probald ujra rovidebb" not in lowered, "planning must not use retry-shorter fallback text")


def test_91_planning_structured_json_path_used() -> None:
    chat_id = "golden-plan-91"
    out = _daily_planning_chat_output(chat_id, PLANNING_TODAY_HU_MESSAGE)
    assert_true("1) " not in out and "2) " not in out and "3) " not in out, "plain output should not contain numbered template headers")
    path = db_scalar(
        "SELECT COALESCE(metadata->>'generation_path','') FROM interaction_events "
        f"WHERE role='assistant' AND COALESCE(metadata->>'chat_id','')='{chat_id}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    )
    assert_true(path == "planning_structured", "planning chat should use structured JSON generation path")


def test_92_api_health_works() -> None:
    client = api_client()
    resp = client.get("/v1/health")
    assert_true(resp.status_code == 200, "GET /v1/health should return 200")
    out = resp.json()
    assert_true(out.get("status") == "ok", "health status must be ok")
    assert_true("version" in out and "db" in out and "api_port" in out, "health payload missing required fields")
    assert_true(out.get("api_port") == 8094 and out.get("ui_port") == 8093, "health ports should be fixed values")


def test_92b_health_includes_backend_status_and_breaker() -> None:
    client = api_client()
    out = client.get("/v1/health").json()
    assert_true("generator_backends" in out, "health must include generator_backends")
    assert_true("breaker" in out, "health must include breaker state")
    gb = out["generator_backends"]
    assert_true("mlx" in gb and "ollama" in gb, "health must report mlx and ollama availability")
    br = out["breaker"]
    assert_true("mlx" in br and "ollama" in br, "breaker state must include mlx and ollama keys")


def test_93_api_respond_requires_token_401() -> None:
    old = os.environ.get("HATORI_API_TOKEN")
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    try:
        client = api_client()
        resp = client.post(
            "/v1/agent/respond",
            json={"conversation_id": "reply:test-93", "message_id": "reply:m93", "sender_id": "reply:u93", "message": "hello"},
        )
        assert_true(resp.status_code == 401, "POST /v1/agent/respond should require token")
    finally:
        if old is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old


def test_93b_api_auth_required_for_post_endpoints() -> None:
    old = os.environ.get("HATORI_API_TOKEN")
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    try:
        client = api_client()
        assistant_id = db_scalar("SELECT id FROM interaction_events WHERE role='assistant' ORDER BY occurred_at DESC LIMIT 1;")
        r1 = client.post(
            "/v1/agent/feedback",
            json={"assistant_interaction_id": assistant_id, "vote": "up", "category": "Other"},
        )
        r2 = client.post(
            "/v1/ingest/event",
            json={"external_event_id": "reply:test-93b", "kind": "note", "content": "auth check"},
        )
        assert_true(r1.status_code == 401, "POST /v1/agent/feedback should require token")
        assert_true(r2.status_code == 401, "POST /v1/ingest/event should require token")
    finally:
        if old is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old


def test_94_api_respond_creates_two_interactions_linked() -> None:
    old = os.environ.get("HATORI_API_TOKEN")
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    try:
        client = api_client()
        cid = "reply:test-94"
        resp = client.post(
            "/v1/agent/respond",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "conversation_id": cid,
                "message_id": "reply:m94",
                "sender_id": "reply:u94",
                "message": "Szia, kérlek készíts rövid napi tervet.",
                "metadata": {"platform": "imessage", "channel": "sms"},
            },
        )
        assert_true(resp.status_code == 200, "POST /v1/agent/respond should return 200")
        out = resp.json()
        assert_true(out.get("conversation_id") == cid, "response should preserve conversation_id")
        assert_true(out.get("message_id") == "reply:m94", "response should return message_id")
        user_id = out.get("user_interaction_id", "")
        assistant_id = out.get("assistant_interaction_id", "")
        assert_true(bool(user_id) and bool(assistant_id), "respond should return created interaction ids")
        assert_true(bool(out.get("backend_used", "")), "respond should return backend_used machine field")
        assert_true(isinstance(out.get("backend_fallback_used"), bool), "respond should return backend_fallback_used bool")
        linked = db_scalar(
            "SELECT count(*) FROM interaction_events "
            f"WHERE id='{assistant_id}' AND COALESCE(metadata->>'related_user_interaction_id','')='{user_id}';"
        )
        assert_true(int(linked) == 1, "assistant interaction must link to user interaction id")
    finally:
        if old is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old


def test_95_api_feedback_creates_learning_event_linked() -> None:
    old = os.environ.get("HATORI_API_TOKEN")
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    try:
        client = api_client()
        respond = client.post(
            "/v1/agent/respond",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "conversation_id": "reply:test-95",
                "message_id": "reply:m95",
                "sender_id": "reply:u95",
                "message": "hello from api feedback path",
            },
        )
        assistant_id = respond.json()["assistant_interaction_id"]
        before = int(db_scalar("SELECT count(*) FROM learning_events;"))
        fb = client.post(
            "/v1/agent/feedback",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "assistant_interaction_id": assistant_id,
                "vote": "down",
                "category": "Relevance",
                "comment": "not focused",
                "external_request_id": "reply:fb95",
            },
        )
        assert_true(fb.status_code == 200, "feedback endpoint should return 200")
        lid = fb.json().get("learning_event_id", "")
        assert_true(bool(lid), "feedback should return learning_event_id")
        after = int(db_scalar("SELECT count(*) FROM learning_events;"))
        assert_true(after == before + 1, "feedback should create one learning_event row")
        linked = db_scalar(
            "SELECT count(*) FROM learning_events "
            f"WHERE id='{lid}' AND related_interaction_id='{assistant_id}';"
        )
        assert_true(int(linked) == 1, "learning event should link to assistant interaction")
    finally:
        if old is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old


def test_96_api_ingest_event_idempotent() -> None:
    old = os.environ.get("HATORI_API_TOKEN")
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    try:
        client = api_client()
        event_id = "reply:event-96"
        one = client.post(
            "/v1/ingest/event",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "external_event_id": event_id,
                "kind": "imessage",
                "conversation_id": "reply:conv-96",
                "sender_id": "reply:u96",
                "content": "first content",
                "metadata": {"platform": "imessage"},
            },
        )
        two = client.post(
            "/v1/ingest/event",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "external_event_id": event_id,
                "kind": "imessage",
                "conversation_id": "reply:conv-96",
                "sender_id": "reply:u96",
                "content": "first content",
                "metadata": {"platform": "imessage"},
            },
        )
        assert_true(one.status_code == 200 and two.status_code == 200, "ingest endpoint should return 200")
        iid1 = one.json().get("interaction_id")
        iid2 = two.json().get("interaction_id")
        assert_true(iid1 == iid2, "idempotent ingest should return same interaction_id for duplicate event_id")
        cnt = db_scalar(
            "SELECT count(*) FROM interaction_events "
            f"WHERE COALESCE(metadata->>'external_event_id','')='{event_id}' "
            "AND COALESCE(metadata->>'source','')='reply.ingest_event';"
        )
        assert_true(int(cnt) == 1, "idempotent ingest must not create duplicate rows")
    finally:
        if old is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old


def test_97_api_search_returns_human_readable_only() -> None:
    old = os.environ.get("HATORI_API_TOKEN")
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    try:
        client = api_client()
        resp = client.get(
            "/v1/search",
            params={"q": "NightlyWarmupChecklistToken", "k": 5},
            headers={"X-Hatori-Token": "golden-token"},
        )
        assert_true(resp.status_code == 200, "search endpoint should return 200")
        rows = resp.json()
        txt = json.dumps(rows, ensure_ascii=False).lower()
        assert_true("emb:" not in txt and "artefact_id" not in txt, "search output should not include internal IDs")
        uuid_any_re = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)
        assert_true(uuid_any_re.search(txt) is None, "search output should not include UUID values")
    finally:
        if old is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old


def test_98_api_upload_creates_artefact_and_embeddings_txt() -> None:
    old = os.environ.get("HATORI_API_TOKEN")
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    try:
        client = api_client()
        before_art = int(db_scalar("SELECT count(*) FROM artefacts;"))
        before_emb = int(db_scalar("SELECT count(*) FROM embeddings;"))
        with UPLOAD_FIXTURE.open("rb") as fh:
            resp = client.post(
                "/v1/artefacts/upload",
                headers={"X-Hatori-Token": "golden-token"},
                files={"file": (UPLOAD_FIXTURE.name, fh, "text/plain")},
                data={"external_event_id": "reply:upload-98", "kind": "doc"},
            )
        assert_true(resp.status_code == 200, "POST /v1/artefacts/upload should return 200")
        out = resp.json()
        assert_true(bool(out.get("artefact_id")), "upload should return artefact_id")
        assert_true(bool(out.get("sha256")), "upload should return sha256")
        assert_true(int(out.get("chunks_created", 0)) > 0, "txt upload should create embedding chunks")
        after_art = int(db_scalar("SELECT count(*) FROM artefacts;"))
        after_emb = int(db_scalar("SELECT count(*) FROM embeddings;"))
        assert_true(after_art == before_art + 1, "upload should create one artefact row")
        assert_true(after_emb > before_emb, "upload should create embeddings")
    finally:
        if old is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old


def test_99_api_ingest_path_rejected_by_default() -> None:
    old_token = os.environ.get("HATORI_API_TOKEN")
    old_allow = os.environ.get("HATORI_ALLOW_PATH_INGEST")
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    os.environ.pop("HATORI_ALLOW_PATH_INGEST", None)
    try:
        client = api_client()
        resp = client.post(
            "/v1/artefacts/ingest_path",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "external_event_id": "reply:path-99",
                "kind": "doc",
                "path": str(UPLOAD_FIXTURE),
            },
        )
        assert_true(resp.status_code == 403, "ingest_path must be disabled by default")
    finally:
        if old_token is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old_token
        if old_allow is None:
            os.environ.pop("HATORI_ALLOW_PATH_INGEST", None)
        else:
            os.environ["HATORI_ALLOW_PATH_INGEST"] = old_allow


def test_100_api_outcome_sent_as_is_creates_delivery_event_and_positive_learning() -> None:
    old = os.environ.get("HATORI_API_TOKEN")
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    try:
        client = api_client()
        respond = client.post(
            "/v1/agent/respond",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "conversation_id": "reply:test-100",
                "message_id": "reply:m100",
                "sender_id": "reply:u100",
                "message": "Szia, írj rövid választ.",
            },
        )
        assert_true(respond.status_code == 200, "respond should return 200")
        assistant_id = respond.json()["assistant_interaction_id"]
        assert_true(bool(respond.json().get("assistant_message", "").strip()), "respond should return assistant_message")
        assert_true(respond.json().get("message_id") == "reply:m100", "respond should return message_id")
        before = int(db_scalar("SELECT count(*) FROM learning_events WHERE kind='PositiveFeedback';"))
        before_delivery = int(db_scalar("SELECT count(*) FROM delivery_events;"))
        out = client.post(
            "/v1/agent/outcome",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "external_outcome_id": "reply:outcome-100",
                "assistant_interaction_id": assistant_id,
                "status": "sent_as_is",
                "platform": "imessage",
                "conversation_id": "reply:test-100",
            },
        )
        assert_true(out.status_code == 200, "outcome endpoint should accept sent_as_is")
        after = int(db_scalar("SELECT count(*) FROM learning_events WHERE kind='PositiveFeedback';"))
        after_delivery = int(db_scalar("SELECT count(*) FROM delivery_events;"))
        assert_true(after == before + 1, "sent_as_is should create PositiveFeedback learning event")
        assert_true(after_delivery == before_delivery + 1, "sent_as_is should create delivery_events row")
        dcount = int(
            db_scalar(
                "SELECT count(*) FROM delivery_events "
                "WHERE external_outcome_id='reply:outcome-100' "
                f"AND assistant_interaction_id='{assistant_id}' "
                "AND status='sent_as_is';"
            )
        )
        assert_true(dcount == 1, "delivery_events row should be linked and auditable")
    finally:
        if old is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old


def test_101_api_outcome_edited_then_sent_creates_delivery_event_and_negative_learning_with_texts() -> None:
    old = os.environ.get("HATORI_API_TOKEN")
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    try:
        client = api_client()
        respond = client.post(
            "/v1/agent/respond",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "conversation_id": "reply:test-101",
                "message_id": "reply:m101",
                "sender_id": "reply:u101",
                "message": "Kérlek írj rövid üzenetet.",
            },
        )
        assistant_id = respond.json()["assistant_interaction_id"]
        original_text = (respond.json().get("assistant_message") or "").strip()
        final_text = "Szia! Holnap 10-kor jó neked?"
        diff_text = "- Bőbeszédű javaslat\n+ Rövid, közvetlen egyeztető üzenet"
        out = client.post(
            "/v1/agent/outcome",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "external_outcome_id": "reply:outcome-101",
                "assistant_interaction_id": assistant_id,
                "status": "edited_then_sent",
                "platform": "imessage",
                "original_text": original_text,
                "final_sent_text": final_text,
                "diff": diff_text,
                "edit_reason": "too long",
            },
        )
        assert_true(out.status_code == 200, "outcome endpoint should accept edited_then_sent")
        row_count = int(
            db_scalar(
                "SELECT count(*) FROM learning_events "
                f"WHERE kind='NegativeFeedback' AND related_interaction_id='{assistant_id}' "
                "AND COALESCE(details->>'external_outcome_id','')='reply:outcome-101' "
                f"AND COALESCE(details->>'final_sent_text','')='{sql_escape(final_text)}';"
            )
        )
        assert_true(row_count == 1, "edited_then_sent should log NegativeFeedback with external_outcome_id and final text")
        diff_logged = db_scalar(
            "SELECT COALESCE(details->>'diff','') FROM learning_events "
            f"WHERE kind='NegativeFeedback' AND related_interaction_id='{assistant_id}' "
            "AND COALESCE(details->>'external_outcome_id','')='reply:outcome-101' "
            "ORDER BY occurred_at DESC LIMIT 1;"
        )
        assert_true("Rövid, közvetlen" in diff_logged or "Rovid, kozvetlen" in diff_logged, "learning event should preserve diff/edit summary")
        dcount = int(
            db_scalar(
                "SELECT count(*) FROM delivery_events "
                f"WHERE external_outcome_id='reply:outcome-101' AND assistant_interaction_id='{assistant_id}' "
                f"AND COALESCE(original_text,'')='{sql_escape(original_text)}' "
                f"AND COALESCE(final_sent_text,'')='{sql_escape(final_text)}' "
                f"AND COALESCE(diff,'')='{sql_escape(diff_text)}';"
            )
        )
        assert_true(dcount == 1, "delivery_events should capture original_text/final_sent_text/diff")
    finally:
        if old is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old


def test_102_api_outcome_idempotency_blocks_duplicates() -> None:
    old = os.environ.get("HATORI_API_TOKEN")
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    try:
        client = api_client()
        respond = client.post(
            "/v1/agent/respond",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "conversation_id": "reply:test-102",
                "message_id": "reply:m102",
                "sender_id": "reply:u102",
                "message": "Rövid válasz kérés",
            },
        )
        assistant_id = respond.json()["assistant_interaction_id"]
        payload = {
            "external_outcome_id": "reply:outcome-102",
            "assistant_interaction_id": assistant_id,
            "status": "sent_as_is",
            "platform": "imessage",
        }
        one = client.post("/v1/agent/outcome", headers={"X-Hatori-Token": "golden-token"}, json=payload)
        two = client.post("/v1/agent/outcome", headers={"X-Hatori-Token": "golden-token"}, json=payload)
        assert_true(one.status_code == 200 and two.status_code == 200, "repeated outcome calls should be accepted")
        lid1 = one.json().get("learning_event_id", "")
        lid2 = two.json().get("learning_event_id", "")
        did1 = one.json().get("delivery_event_id", "")
        did2 = two.json().get("delivery_event_id", "")
        assert_true(lid1 == lid2, "duplicate outcome must return same learning_event_id")
        assert_true(did1 == did2, "duplicate outcome must return same delivery_event_id")
        cnt = int(
            db_scalar(
                "SELECT count(*) FROM learning_events "
                "WHERE COALESCE(details->>'external_outcome_id','')='reply:outcome-102';"
            )
        )
        assert_true(cnt == 1, "idempotent outcome must not duplicate learning events")
        dcnt = int(db_scalar("SELECT count(*) FROM delivery_events WHERE external_outcome_id='reply:outcome-102';"))
        assert_true(dcnt == 1, "idempotent outcome must not duplicate delivery_events rows")
    finally:
        if old is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old


def test_103_api_outcome_requires_token_401() -> None:
    client = api_client()
    out = client.post(
        "/v1/agent/outcome",
        json={
            "external_outcome_id": "reply:outcome-103",
            "assistant_interaction_id": str(uuid.uuid4()),
            "status": "sent_as_is",
        },
    )
    assert_true(out.status_code == 401, "outcome endpoint should require token")


def test_104_api_outcome_rejects_missing_fields_when_edited() -> None:
    old = os.environ.get("HATORI_API_TOKEN")
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    try:
        client = api_client()
        respond = client.post(
            "/v1/agent/respond",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "conversation_id": "reply:test-104",
                "message_id": "reply:m104",
                "sender_id": "reply:u104",
                "message": "Adj rövid szöveget.",
            },
        )
        assistant_id = respond.json()["assistant_interaction_id"]
        out = client.post(
            "/v1/agent/outcome",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "external_outcome_id": "reply:outcome-104",
                "assistant_interaction_id": assistant_id,
                "status": "edited_then_sent",
                "platform": "imessage",
            },
        )
        assert_true(out.status_code == 400, "edited_then_sent must require final_sent_text")
        out2 = client.post(
            "/v1/agent/outcome",
            headers={"X-Hatori-Token": "golden-token"},
            json={
                "external_outcome_id": "reply:outcome-104b",
                "assistant_interaction_id": assistant_id,
                "status": "edited_then_sent",
                "platform": "imessage",
                "final_sent_text": "röviden jó",
            },
        )
        assert_true(out2.status_code == 400, "edited_then_sent must require original_text")
    finally:
        if old is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old


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
        test_34b_model_ollama_adapter_selectable,
        test_34c_gateway_prefers_mlx_when_available,
        test_34d_gateway_fallbacks_to_ollama_on_mlx_failure,
        test_34e_gateway_returns_clean_error_when_all_fail,
        test_34f_gateway_output_still_passes_leakage_validator,
        test_35_consistency_check_offline_pass,
        test_36_consistency_check_json_shape,
        test_37_no_A_H_write_during_ask,
        test_38_consistency_check_detects_violation_fixture,
        test_39_pending_rule_static_guard_present,
        test_40_prompt_builder_single_path_for_template,
        test_41_consistency_check_reports_pks_summary,
        test_42_model_healthcheck_none_ok,
        test_43_chat_get_returns_200,
        test_44_chat_send_creates_user_and_assistant_rows,
        test_45_chat_send_metadata_linking,
        test_46_feedback_up_creates_positive_learning,
        test_47_feedback_down_requires_context,
        test_48_feedback_down_creates_negative_learning,
        test_49_upload_txt_creates_artefact_and_embeddings,
        test_50_upload_content_searchable_in_ui,
        test_60_planning_today_hu_language_mirror,
        test_61_planning_today_includes_default_template_sections,
        test_62_planning_today_assumptions_present_when_calendar_unknown,
        test_63_planning_today_next_actions_count_and_priority,
        test_64_planning_today_no_web_claims_offline,
        test_65_planning_today_no_memory_patch_by_default,
        test_66_planning_today_learning_log_default,
        test_67_planning_today_no_fabricated_commitments,
        test_68_chat_no_prompt_leakage_markers,
        test_69_chat_hungarian_language_mirror,
        test_70_chat_template_sections_present,
        test_71_chat_no_placeholder_markers,
        test_72_chat_decline_feedback_logging_unchanged,
        test_73_chat_sanitizer_repair_path,
        test_74_chat_ollama_down_returns_clean_error_not_stub,
        test_75_chat_new_chat_id_default_no_seed_messages,
        test_76_chat_filters_by_chat_id_only,
        test_77_chat_enter_send_shift_enter_newline,
        test_78_chat_no_scaffolding_markers,
        test_79_chat_language_mirror_hu_no_english_leak,
        test_80_chat_uses_history_for_followup,
        test_81_chat_greeting_only_asks_clarifying_question_hu,
        test_82_chat_preview_does_not_show_template_headers,
        test_83_chat_no_policy_dump_markers,
        test_84_utf8_roundtrip_hu_message,
        test_85_chat_no_uuid_or_emb_ids_in_output,
        test_86_chat_no_user_request_echo,
        test_87_chat_sources_are_human_readable_only,
        test_88_chat_repair_triggers_on_uuid_leak,
        test_89_planning_today_returns_real_plan_hu,
        test_90_planning_today_never_refusal_fallback,
        test_91_planning_structured_json_path_used,
        test_92_api_health_works,
        test_92b_health_includes_backend_status_and_breaker,
        test_93_api_respond_requires_token_401,
        test_93b_api_auth_required_for_post_endpoints,
        test_94_api_respond_creates_two_interactions_linked,
        test_95_api_feedback_creates_learning_event_linked,
        test_96_api_ingest_event_idempotent,
        test_97_api_search_returns_human_readable_only,
        test_98_api_upload_creates_artefact_and_embeddings_txt,
        test_99_api_ingest_path_rejected_by_default,
        test_100_api_outcome_sent_as_is_creates_delivery_event_and_positive_learning,
        test_101_api_outcome_edited_then_sent_creates_delivery_event_and_negative_learning_with_texts,
        test_102_api_outcome_idempotency_blocks_duplicates,
        test_103_api_outcome_requires_token_401,
        test_104_api_outcome_rejects_missing_fields_when_edited,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--subset", type=int, default=0)
    args, _unknown = parser.parse_known_args()

    old_model = os.environ.get("HATORI_MODEL")
    old_api_token = os.environ.get("HATORI_API_TOKEN")
    os.environ["HATORI_MODEL"] = "none"
    os.environ["HATORI_API_TOKEN"] = "golden-token"
    try:
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
    finally:
        if old_model is None:
            os.environ.pop("HATORI_MODEL", None)
        else:
            os.environ["HATORI_MODEL"] = old_model
        if old_api_token is None:
            os.environ.pop("HATORI_API_TOKEN", None)
        else:
            os.environ["HATORI_API_TOKEN"] = old_api_token


if __name__ == "__main__":
    main()
