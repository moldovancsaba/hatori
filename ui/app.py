import hashlib
import html
import json
import mimetypes
import os
from datetime import datetime
from pathlib import Path
import re
import subprocess
import uuid

from fastapi import FastAPI
from fastapi import File
from fastapi import Form
from fastapi import UploadFile
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse

from hatori.embeddings import get_embeddings_adapter
from hatori.model import get_model_adapter
from hatori.model import OllamaAdapter
from hatori.model import prefer_ollama_if_available
from hatori.prompts import build_system_prompt
from hatori.prompts import build_task_prompt
from hatori.cli import search_runtime

CID = os.environ.get("CID", "hatori-pg")
UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
UUID_ANY_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)
ROOT_DIR = Path(__file__).resolve().parent.parent
EXPORT_DIR = ROOT_DIR / "artefacts" / "exports"
UPLOAD_DIR = ROOT_DIR / "artefacts" / "uploads"

app = FastAPI()

CSS = (
    "body{font-family:system-ui;max-width:1100px;margin:24px auto;padding:0 16px}"
    " a{color:#0a58ca;text-decoration:none} a:hover{text-decoration:underline}"
    " .top{display:flex;justify-content:space-between;align-items:center;gap:10px}"
    " .brand{font-size:42px;font-weight:800}"
    " .nav a{margin-right:14px;font-weight:600}"
    " .card{border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px;margin:12px 0}"
    " pre{white-space:pre-wrap;background:#f8fafc;border:1px solid #e5e7eb;border-radius:10px;padding:12px}"
    " .msg-user{background:#eef6ff;border:1px solid #b6d4ff;padding:10px;border-radius:8px;margin:8px 0}"
    " .msg-assistant{background:#f8fafc;border:1px solid #dfe4ea;padding:10px;border-radius:8px;margin:8px 0}"
    " .msg-body{white-space:pre-wrap}"
    " .chat-wrap{display:flex;gap:16px;align-items:flex-start}"
    " .chat-side{width:280px;position:sticky;top:12px}"
    " .chat-main{flex:1;min-width:0}"
    " .chat-item{padding:8px;border:1px solid #e5e7eb;border-radius:8px;margin:8px 0;display:block}"
    " .chat-item small{color:#6b7280;display:block}"
    " .chat-actions{display:flex;gap:8px;margin:8px 0}"
    " .ts{color:#6b7280;font-size:12px}"
    " input[type=text],textarea,select{width:100%;padding:8px;margin:6px 0}"
    " button{padding:6px 10px}"
)


def _esc_sql(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "''")


def _h(s: str) -> str:
    return html.escape(s, quote=True)


def psql(sql: str) -> str:
    cmd = ["docker", "exec", "-i", CID, "psql", "-U", "hatori", "-d", "hatori", "-t", "-A", "-F", "|", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "psql failed")
    return r.stdout.strip()


def psql_json(sql: str) -> list[dict]:
    wrapped = f"SELECT COALESCE(json_agg(t), '[]'::json) FROM ({sql}) t;"
    out = psql(wrapped)
    if not out:
        return []
    return json.loads(out)


def insert_interaction(role: str, content: str, metadata: dict) -> str:
    iid = str(uuid.uuid4())
    meta = _esc_sql(json.dumps(metadata, ensure_ascii=False))
    sql = (
        "INSERT INTO interaction_events (id, role, content, metadata) "
        f"VALUES ('{iid}', '{_esc_sql(role)}', '{_esc_sql(content)}', '{meta}'::jsonb);"
    )
    psql(sql)
    return iid


def insert_learning(kind: str, confidence: str, details: dict, related_interaction_id: str) -> str:
    lid = str(uuid.uuid4())
    det = _esc_sql(json.dumps(details, ensure_ascii=False))
    sql = (
        "INSERT INTO learning_events (id, kind, confidence, details, related_interaction_id) "
        f"VALUES ('{lid}', '{_esc_sql(kind)}', '{_esc_sql(confidence)}', '{det}'::jsonb, '{_esc_sql(related_interaction_id)}');"
    )
    psql(sql)
    return lid


def audit(action: str, target_type: str, target_id: str, details: dict) -> None:
    det = _esc_sql(json.dumps(details, ensure_ascii=False))
    sql = (
        "INSERT INTO audit_events (id, actor, action, target_type, target_id, details) "
        f"VALUES (gen_random_uuid(), 'ui', '{_esc_sql(action)}', '{_esc_sql(target_type)}', '{_esc_sql(target_id)}', '{det}'::jsonb);"
    )
    psql(sql)


def vector_sql_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vector) + "]"


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append(clean[start:end])
        if end == len(clean):
            break
        start = max(0, end - overlap)
    return chunks


def new_chat_id() -> str:
    return str(uuid.uuid4())


def load_chat_rows(chat_id: str, limit: int = 300) -> list[dict]:
    return psql_json(
        "SELECT id, occurred_at, role, content, metadata "
        "FROM interaction_events "
        f"WHERE COALESCE(metadata->>'chat_id','')='{_esc_sql(chat_id)}' "
        "AND role IN ('user','assistant') "
        "ORDER BY occurred_at ASC "
        f"LIMIT {int(limit)}"
    )


def load_recent_chats(limit: int = 40) -> list[dict]:
    return psql_json(
        "SELECT t.chat_id, t.occurred_at AS last_at, t.role AS last_role, t.content AS last_content, "
        "  (SELECT iu.content FROM interaction_events iu "
        "   WHERE COALESCE(iu.metadata->>'chat_id','')=t.chat_id AND iu.role='user' "
        "   ORDER BY iu.occurred_at DESC LIMIT 1) AS last_user_content "
        "FROM ("
        "  SELECT DISTINCT ON (COALESCE(metadata->>'chat_id','')) "
        "    COALESCE(metadata->>'chat_id','') AS chat_id, occurred_at, role, content, metadata "
        "  FROM interaction_events "
        "  WHERE COALESCE(metadata->>'chat_id','') <> '' "
        "    AND role IN ('user','assistant') "
        "    AND COALESCE(metadata->>'archived','false') <> 'true' "
        "  ORDER BY COALESCE(metadata->>'chat_id',''), occurred_at DESC"
        ") t "
        "ORDER BY t.occurred_at DESC "
        f"LIMIT {int(limit)}"
    )


def load_chat_history_for_prompt(chat_id: str, limit: int = 10) -> list[dict]:
    rows = psql_json(
        "SELECT role, content, occurred_at "
        "FROM interaction_events "
        f"WHERE COALESCE(metadata->>'chat_id','')='{_esc_sql(chat_id)}' "
        "AND role IN ('user','assistant') "
        "ORDER BY occurred_at DESC "
        f"LIMIT {int(limit)}"
    )
    rows.reverse()
    return rows


def load_pks_context(limit: int = 8) -> list[dict]:
    return psql_json(
        "SELECT module, status, title, body "
        "FROM pks_records "
        "WHERE status='Approved' "
        "ORDER BY updated_at DESC "
        f"LIMIT {int(limit)}"
    )


def load_local_evidence_context(query: str, limit: int = 6) -> list[dict]:
    payload = search_runtime(query=query, limit=int(limit), allow_pending=False)
    return payload.get("results", [])[: int(limit)]


def summarize_prev_user_turn(history: list[dict]) -> str:
    for row in reversed(history):
        if (row.get("role") or "").lower() == "user":
            txt = (row.get("content") or "").strip()
            if txt:
                return txt[:120]
    return ""


def _short_path(path: str) -> str:
    p = (path or "").strip()
    if not p:
        return ""
    parts = p.split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return p


def summarize_pks_for_model(rows: list[dict], limit: int = 4) -> list[dict]:
    out: list[dict] = []
    for row in rows[: max(0, int(limit))]:
        out.append(
            {
                "title": (row.get("title") or "").strip()[:120],
                "status": (row.get("status") or "").strip(),
                "summary": (row.get("body") or "").strip()[:180],
            }
        )
    return out


def summarize_evidence_for_model(rows: list[dict], limit: int = 4) -> list[dict]:
    out: list[dict] = []
    for row in rows[: max(0, int(limit))]:
        uri = (row.get("artefact_uri") or "").strip()
        filename = os.path.basename(uri) if uri else ""
        out.append(
            {
                "filename": filename or _short_path(uri),
                "provenance": (row.get("provenance") or "").strip(),
                "excerpt": (row.get("excerpt") or "").strip()[:160],
            }
        )
    return out


def build_human_sources_lines(language_code: str, pks_rows: list[dict], evidence_rows: list[dict]) -> list[str]:
    pks_titles = [r.get("title", "").strip() for r in pks_rows if (r.get("title") or "").strip()]
    pks_titles = pks_titles[:3]
    docs: list[str] = []
    for row in evidence_rows:
        uri = (row.get("artefact_uri") or "").strip()
        name = os.path.basename(uri) if uri else ""
        if name:
            docs.append(name)
    docs = docs[:5]
    lines: list[str] = []
    if language_code == "hu":
        if pks_titles:
            lines.append(f"PKS (Approved): {'; '.join(pks_titles)}")
        if docs:
            lines.append(f"Helyi dokumentumok: {'; '.join(docs)}")
        if not lines:
            lines.append("Nincs helyi bizonyíték.")
        return lines
    if pks_titles:
        lines.append(f"Approved PKS: {'; '.join(pks_titles)}")
    if docs:
        lines.append(f"Local documents: {'; '.join(docs)}")
    if not lines:
        lines.append("No local evidence found.")
    return lines


def extract_project_name_from_history(history: list[dict]) -> str:
    for row in reversed(history):
        if (row.get("role") or "").lower() != "user":
            continue
        text = (row.get("content") or "").strip()
        if not text:
            continue
        hu = re.search(r"\bprojekt neve\s+([A-Za-z0-9_.-]{2,80})", text, flags=re.IGNORECASE)
        if hu:
            return hu.group(1).strip(".,;:!?")
        en = re.search(r"\bproject name is\s+([A-Za-z0-9_.-]{2,80})", text, flags=re.IGNORECASE)
        if en:
            return en.group(1).strip(".,;:!?")
    return ""


def resolve_followup_from_history(user_text: str, history: list[dict], language_code: str) -> str:
    lowered = user_text.strip().lower()
    asks_project_name = (
        ("projekt neve" in lowered)
        or ("mi a projekt neve" in lowered)
        or ("project name" in lowered)
        or ("what is the project name" in lowered)
    )
    if not asks_project_name:
        return ""
    project_name = extract_project_name_from_history(history)
    if not project_name:
        return ""
    if language_code == "hu":
        return f"A korábbi üzenet alapján a projekt neve: {project_name}."
    return f"Based on the previous message, the project name is: {project_name}."


def detect_message_language(text: str) -> str:
    sample = text.strip().lower()
    if not sample:
        return "en"

    if re.search(r"[ăâîșț]", sample) or re.search(r"\b(și|sunt|este|pentru|cum|te rog)\b", sample):
        return "ro"
    if re.search(r"[áéíóöőúüű]", sample) or re.search(r"\b(szia|és|vagy|kérlek|kerlek|miért|miert|hogyan|nem)\b", sample):
        return "hu"
    if re.search(r"[ñ¿¡]", sample) or re.search(r"\b(que|como|por|favor|gracias|respuesta)\b", sample):
        return "es"
    if re.search(r"\b(le|la|les|des|bonjour|merci|avec)\b", sample):
        return "fr"
    if re.search(r"\b(und|der|die|das|bitte|danke|nicht)\b", sample):
        return "de"
    return "en"


def language_name(code: str) -> str:
    return {
        "ro": "Romanian",
        "hu": "Hungarian",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "en": "English",
    }.get(code, "English")


def localized_model_error(code: str, err: str) -> str:
    if code == "ro":
        return f"Eroare model local: {err}"
    if code == "hu":
        return f"Helyi modellhiba: {err}"
    if code == "es":
        return f"Error del modelo local: {err}"
    if code == "fr":
        return f"Erreur du modele local: {err}"
    if code == "de":
        return f"Lokaler Modellfehler: {err}"
    return f"Local model error: {err}"


FORBIDDEN_SCAFFOLD_MARKERS = [
    "task prompt",
    "retrieved pks",
    "required behaviour",
    "active project",
    "connectivity:",
    "time:",
    "local evidence snippets",
    "hatori runtime system",
    "charter v3",
    "folytatás:",
    "canonical task template source",
    "[null-adapter:",
    "nulladapter",
    "fingerprint:",
    "follow charter",
    "követelmények",
    "kovetelmenyek",
    "rendelkezések megfeleléséhez",
    "rendelkezesek megfelelesehez",
    "memory patch",
    "learning log",
    "tanulási napló",
    "tanulasi naplo",
    "required behavior",
]

FORBIDDEN_USER_VISIBLE_MARKERS = [
    "emb:",
    "artefact_id",
    "retrieved pks",
    "user request:",
    "state assumptions",
    "cite provenance",
    "follow charter",
    "required behaviour",
]


def sanitize_assistant_output(text: str) -> str:
    sanitized, _removed_ratio = _sanitize_with_stats(text)
    return sanitized


def _sanitize_with_stats(text: str) -> tuple[str, float]:
    original = text or ""
    kept_lines: list[str] = []
    removed_chars = 0
    for raw in original.splitlines():
        line = raw.strip()
        lowered = line.lower()
        if re.match(r"^\s*[1-7]\)\s+", line):
            removed_chars += len(raw)
            continue
        if "```" in line:
            removed_chars += len(raw)
            continue
        if any(marker in lowered for marker in FORBIDDEN_SCAFFOLD_MARKERS):
            removed_chars += len(raw)
            continue
        kept_lines.append(raw)
    cleaned = "\n".join(kept_lines).strip()
    if not cleaned:
        return "", 1.0
    ratio = min(1.0, removed_chars / max(1, len(original)))
    return cleaned, ratio


def _needs_repair(raw: str, cleaned: str, removed_ratio: float) -> bool:
    if not cleaned:
        return True
    if removed_ratio > 0.30:
        return True
    return len(cleaned.strip()) < 48


def _looks_hungarian(text: str) -> bool:
    lowered = text.lower()
    markers = ["szia", "kérlek", "kerlek", "ma", "feladat", "feltételezés", "feltetelezes", "következő", "kovetkezo"]
    hits = sum(1 for m in markers if m in lowered)
    has_hu_chars = bool(re.search(r"[áéíóöőúüű]", lowered))
    return has_hu_chars or hits >= 2


def _repair_assistant_output(model, language_code: str, user_text: str, leaked_text: str) -> str:
    strict = (
        f"Rewrite ONLY the final user-facing answer in {language_name(language_code)}.\n"
        "Follow the 7-section template only.\n"
        "Do not include any internal prompts, metadata, scaffolding, or code fences.\n"
        "Do not include lines like TASK PROMPT, Retrieved PKS, Required behaviour, Connectivity:, Time:, Active Project.\n"
        f"User request: {user_text}\n"
        f"Draft to repair: {leaked_text}\n"
    )
    repaired = model.generate(system_prompt="Output cleaner.", task_prompt=strict).strip()
    repaired_sanitized = sanitize_assistant_output(repaired)
    if not repaired_sanitized:
        raise RuntimeError("repair produced empty output")
    return repaired_sanitized


def _repair_assistant_output_idsafe(model, language_code: str, user_text: str, leaked_text: str) -> str:
    strict = (
        f"Rewrite ONLY the final user-facing answer in {language_name(language_code)}.\n"
        "Do not include any IDs, UUIDs, emb:, metadata, internal notes, or user request echo.\n"
        "Evidence & Sources must list human-readable titles/filenames only.\n"
        "Do not include tool scaffolding or instruction bullets.\n"
        f"User message: {user_text}\n"
        f"Draft to repair: {leaked_text}\n"
    )
    repaired = model.generate(system_prompt="User-visible output repair.", task_prompt=strict).strip()
    repaired_sanitized = sanitize_assistant_output(repaired)
    if not repaired_sanitized:
        raise RuntimeError("id-safe repair produced empty output")
    return repaired_sanitized


def _has_forbidden_user_visible_markers(text: str) -> bool:
    lowered = (text or "").lower()
    if UUID_ANY_RE.search(lowered):
        return True
    return any(m in lowered for m in FORBIDDEN_USER_VISIBLE_MARKERS)


def select_chat_model_adapter():
    explicit = os.environ.get("HATORI_MODEL", "").strip().lower()
    if explicit:
        return get_model_adapter(), None
    if prefer_ollama_if_available():
        return OllamaAdapter(), None
    return None, "Ollama not running; start it via brew services start ollama."


def is_daily_planning_request(text: str) -> bool:
    lowered = text.lower()
    markers = [
        "daily plan",
        "weekly plan",
        "plan my day",
        "planning",
        "napi terv",
        "napi",
        "prioritás",
        "prioritas",
        "teendő",
        "teendo",
        "ma",
        "heti terv",
        "tervez",
        "ütemez",
    ]
    return any(m in lowered for m in markers)


def is_greeting_only(text: str, language_code: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False

    non_greeting_intents = [
        "segíts",
        "segits",
        "kérlek",
        "kerlek",
        "please",
        "help",
        "plan",
        "terv",
        "írj",
        "irj",
        "compose",
        "summarize",
        "search",
        "kutatás",
        "kutatas",
        "döntés",
        "dontes",
    ]
    if any(x in lowered for x in non_greeting_intents):
        return False

    hu_greetings = ["szia", "jó reggelt", "jo reggelt", "szép reggelt", "szep reggelt", "helló", "hello"]
    en_greetings = ["hi", "hello", "good morning", "good afternoon", "good evening", "hey"]
    if language_code == "hu":
        return any(g in lowered for g in hu_greetings)
    if language_code == "en":
        return any(g in lowered for g in en_greetings)
    return False


def greeting_clarifying_answer(language_code: str) -> str:
    if language_code == "hu":
        return "Szia! Miben segíthetek pontosan ma? (pl. napi terv, e-mail, döntés, kutatás)"
    return "Hi! What do you want help with today? (for example: daily plan, email, decision, research)"


def _extract_json_object(raw: str) -> dict | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            loaded = json.loads(text[start:end + 1])
            return loaded if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _normalize_plan_struct(language_code: str, parsed: dict | None) -> tuple[str, list[str], list[str]]:
    answer = ((parsed or {}).get("answer_body") or "").strip()
    assumptions = [str(x).strip() for x in ((parsed or {}).get("assumptions") or []) if str(x).strip()]
    actions = [str(x).strip() for x in ((parsed or {}).get("next_actions") or []) if str(x).strip()]
    answer_has_bad_chars = any(ch in answer for ch in ["�", "±", "\x00"])
    if answer_has_bad_chars or len(answer) < 20:
        answer = ""
    assumptions = [x for x in assumptions if len(x) >= 12 and not any(ch in x for ch in ["�", "±", "\x00"])]
    actions = [x for x in actions if len(x.strip()) >= 12 and not any(ch in x for ch in ["�", "±", "\x00"])]

    if not answer:
        if language_code == "hu":
            answer = "Itt egy rövid, pragmatikus napi terv a mai napra."
        else:
            answer = "Here is a short pragmatic plan for today."

    if not assumptions:
        if language_code == "hu":
            assumptions = [
                "Feltételezés: OFFLINE módban dolgozunk, webes forrás nélkül.",
                "Feltételezés: nincs átadott naptár, fix meeting vagy határidő.",
            ]
        else:
            assumptions = [
                "Assumption: offline mode only, without web sources.",
                "Assumption: no explicit calendar, fixed meetings, or deadlines were provided.",
            ]

    if not actions:
        if language_code == "hu":
            actions = [
                "P0 [ ] Nevezd meg a mai egyetlen legfontosabb eredményt.",
                "P0 [ ] Válassz legfeljebb 3 fókuszfeladatot a mai napra.",
                "P1 [ ] Bontsd a 3 feladatot első konkrét lépésekre.",
                "P1 [ ] Ütemezz 1 admin/kommunikációs tételt.",
                "P1 [ ] Tervezz 1 pufferblokkot megszakításokra.",
                "P2 [ ] Nap végén tarts 10 perces záróértékelést.",
            ]
        else:
            actions = [
                "P0 [ ] Define one most important outcome for today.",
                "P0 [ ] Pick up to 3 focus tasks.",
                "P1 [ ] Break each task into a first concrete step.",
                "P1 [ ] Schedule one admin/coordination item.",
                "P1 [ ] Reserve one buffer block for interruptions.",
                "P2 [ ] Run a 10-minute end-of-day review.",
            ]

    normalized: list[str] = []
    seen_signatures: set[str] = set()
    for idx, action in enumerate(actions, start=1):
        line = action.strip()
        line = re.sub(r"^\-\s*", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if "p0" not in line.lower() and "p1" not in line.lower() and "p2" not in line.lower():
            prefix = "P0" if idx <= 2 else ("P1" if idx <= 5 else "P2")
            line = f"{prefix} [ ] {line}"
        elif "[ ]" not in line:
            line = re.sub(r"^(P[0-2])\s*", r"\1 [ ] ", line, flags=re.IGNORECASE)
        if not re.match(r"^P[0-2]\s+\[\s\]\s+", line, flags=re.IGNORECASE):
            prefix = "P0" if idx <= 2 else ("P1" if idx <= 5 else "P2")
            line = f"{prefix} [ ] {line}"
        line = re.sub(r"^(P[0-2])\s+\[\s\]\s+", lambda m: f"{m.group(1).upper()} [ ] ", line)
        signature = re.sub(r"^P[0-2]\s+\[\s\]\s+", "", line, flags=re.IGNORECASE).lower()
        signature = re.sub(r"[^\wáéíóöőúüű]+", "", signature)
        if signature and signature in seen_signatures:
            continue
        if signature:
            seen_signatures.add(signature)
        normalized.append(line)

    if len(normalized) < 5:
        fallback_hu = [
            "P1 [ ] Blokkold ki az első 45 perces fókuszidőt még most.",
            "P1 [ ] Egyeztess egy rövid státuszfrissítést az érintettekkel.",
            "P2 [ ] Zárd a napot rövid összegzéssel és holnapi első lépéssel.",
        ]
        fallback_en = [
            "P1 [ ] Block the first 45-minute focus slot now.",
            "P1 [ ] Send a short status update to stakeholders.",
            "P2 [ ] Close the day with a short recap and tomorrow first step.",
        ]
        pool = fallback_hu if language_code == "hu" else fallback_en
        for item in pool:
            if len(normalized) >= 5:
                break
            if item not in normalized:
                normalized.append(item)
        while len(normalized) < 5:
            normalized.append(pool[-1])
    normalized = normalized[:8]
    return answer, assumptions[:6], normalized


def generate_planning_structured(model, language_code: str, user_text: str, context: dict) -> tuple[str, list[str], list[str]]:
    if model is None:
        raise RuntimeError("model unavailable")

    prompt = (
        f"Respond in {language_name(language_code)}.\n"
        "Return ONLY valid JSON object, no markdown, no extra text.\n"
        "Schema:\n"
        '{"answer_body":"string","assumptions":["string"],"next_actions":["string"]}\n'
        "Rules:\n"
        "- 5 to 8 next_actions\n"
        "- include priority markers P0/P1/P2 in next_actions\n"
        "- do not include IDs, UUIDs, emb:, metadata, or template headers\n"
        "- do not echo 'User request:'\n"
        f"User message: {user_text}\n"
        f"Context: {json.dumps(context, ensure_ascii=False)}\n"
    )
    raw = model.generate(system_prompt="Planning content generator.", task_prompt=prompt).strip()
    parsed = _extract_json_object(raw)
    if parsed is None:
        retry = (
            f"Return STRICT JSON only in {language_name(language_code)}.\n"
            '{"answer_body":"string","assumptions":["string"],"next_actions":["string"]}\n'
            "No markdown. No explanations.\n"
            f"User message: {user_text}\n"
        )
        raw = model.generate(system_prompt="JSON only.", task_prompt=retry).strip()
        parsed = _extract_json_object(raw)
    return _normalize_plan_struct(language_code, parsed)


def clean_chat_preview(text: str) -> str:
    raw = (text or "").strip().replace("\n", " ")
    if not raw:
        return ""
    raw = re.sub(r"^\s*[1-7]\)\s+[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű /()&:-]+", "", raw).strip()
    sentence = re.split(r"(?<=[.!?])\s+", raw, maxsplit=1)[0]
    out = sentence or raw
    return out[:100] + ("..." if len(out) > 100 else "")


def render_chat_default_output(
    answer: str,
    language_code: str,
    user_text: str,
    sources: list[str] | None = None,
    assumptions_override: list[str] | None = None,
    next_actions_override: list[str] | None = None,
) -> str:
    planning = is_daily_planning_request(user_text)
    source_lines = [s for s in (sources or []) if s.strip()]
    if planning and language_code == "hu":
        assumptions = [
            "Feltételezés: OFFLINE módban dolgozunk, webes forrás nélkül.",
            "Feltételezés: nincs átadott naptár, fix meeting, stakeholder-lista vagy határidő.",
        ]
        next_actions = [
            "- P0 [ ] Ma 1 legfontosabb kimenetet nevezz meg, ami mérhetően lezárható.",
            "- P0 [ ] Becsüld meg a reális kapacitást, majd válassz összesen legfeljebb 3 fókuszfeladatot.",
            "- P1 [ ] Készíts rövid végrehajtási sorrendet a 3 feladathoz (első lépés + kész definíció).",
            "- P1 [ ] Adj hozzá 1 admin/kommunikációs tételt, ami csökkenti a torlódást.",
            "- P1 [ ] Tervezz 1 puffer tételt váratlan megszakításokra.",
            "- P2 [ ] Nap végén tarts 10 perces visszatekintést: mi készült el, mi csúszik, mi a következő lépés.",
        ]
    elif planning:
        assumptions = [
            "Offline local runtime only; no web retrieval used.",
            "No explicit calendar, meetings, stakeholders, or deadlines were provided by the user.",
        ]
        next_actions = [
            "- P0 [ ] Define one measurable top outcome for today.",
            "- P0 [ ] Pick up to three focus tasks aligned with realistic capacity.",
            "- P1 [ ] Sequence the three tasks with a first concrete step each.",
            "- P1 [ ] Add one admin/coordination task to reduce task friction.",
            "- P1 [ ] Add one explicit buffer item for interruptions.",
            "- P2 [ ] End with a short review and tomorrow-first-step note.",
        ]
    else:
        if language_code == "hu":
            assumptions = [
                "Feltételezés: OFFLINE módban dolgozunk, webes forrás nélkül.",
            ]
            next_actions = ["- [ ] Folytasd a beszélgetést egy konkrét következő kérdéssel a pontosításhoz."]
        else:
            assumptions = [
                "Offline local runtime only; no web retrieval used.",
            ]
            next_actions = ["- [ ] Continue the chat with one concrete follow-up question for refinement."]
    if assumptions_override:
        assumptions = [x for x in assumptions_override if str(x).strip()]
    if next_actions_override:
        next_actions = [x for x in next_actions_override if str(x).strip()]
    answer_clean = (answer or "").strip()
    if not planning:
        return answer_clean

    assumptions_text = "\n".join(f"- {x}" for x in assumptions)
    actions_text = "\n".join(next_actions)
    if language_code == "hu":
        parts = [answer_clean]
        if assumptions_text:
            parts.append(f"Feltételezések:\n{assumptions_text}")
        if actions_text:
            parts.append(f"Következő lépések:\n{actions_text}")
        return "\n\n".join([p for p in parts if p.strip()])

    parts = [answer_clean]
    if assumptions_text:
        parts.append(f"Assumptions:\n{assumptions_text}")
    if actions_text:
        parts.append(f"Next actions:\n{actions_text}")
    return "\n\n".join([p for p in parts if p.strip()])


def layout(title: str, inner: str) -> str:
    nav = (
        "<div class='top'><div class='brand'>Hatori</div><div class='nav'>"
        "<a href='/chat'>Chat</a>"
        "<a href='/upload'>Upload</a>"
        "<a href='/search'>Search</a>"
        "<a href='/interactions'>Interactions</a>"
        "<a href='/learning'>Learning</a>"
        "<a href='/pks/pending'>PKS Pending</a>"
        "<a href='/pks/all'>PKS All</a>"
        "<a href='/export.json'>Export JSON</a>"
        "<form style='display:inline; margin-left:8px' method='post' action='/export/disk'><button type='submit'>Export to Disk</button></form>"
        "</div></div>"
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{_h(title)}</title><style>{CSS}</style></head><body>{nav}{inner}</body></html>"
    )


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse(layout("Hatori", "<div class='card'><p>Local dashboard.</p></div>"))


@app.get("/chat/new")
def chat_new() -> RedirectResponse:
    cid = new_chat_id()
    return RedirectResponse(url=f"/chat?chat_id={cid}", status_code=303)


@app.post("/chat/archive")
def chat_archive(chat_id: str = Form(...)) -> RedirectResponse:
    if not chat_id.strip():
        return RedirectResponse(url="/chat?new=1", status_code=303)
    psql(
        "UPDATE interaction_events "
        "SET metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{archived}', 'true'::jsonb, true) "
        f"WHERE COALESCE(metadata->>'chat_id','')='{_esc_sql(chat_id)}';"
    )
    return RedirectResponse(url="/chat?new=1", status_code=303)


@app.get("/chat", response_class=HTMLResponse)
def chat(chat_id: str | None = None, new: int = 0):
    if new == 1 or not (chat_id or "").strip():
        cid = new_chat_id()
        return RedirectResponse(url=f"/chat?chat_id={cid}", status_code=303)

    chat_id = (chat_id or "").strip()
    rows = load_chat_rows(chat_id=chat_id, limit=300)
    recent_chats = load_recent_chats(limit=40)

    body = [f"<div class='chat-wrap'><aside class='chat-side'><div class='card'><h3>Chats</h3>"]
    body.append("<div class='chat-actions'><a href='/chat?new=1'><button type='button'>New chat</button></a></div>")
    for c in recent_chats:
        cid = c.get("chat_id") or ""
        user_preview = clean_chat_preview(c.get("last_user_content") or "")
        fallback_preview = clean_chat_preview(c.get("last_content") or "")
        preview = user_preview or fallback_preview
        body.append(
            f"<a class='chat-item' href='/chat?chat_id={_h(cid)}'>"
            f"<strong>{_h(cid[:8])}</strong>"
            f"<small>{_h(str(c.get('last_at') or ''))}</small>"
            f"<small>{_h(preview)}</small>"
            "</a>"
        )
    body.append("</div></aside><section class='chat-main'><div class='card'>")
    body.append(f"<h2>Chat ({_h(chat_id)})</h2>")
    body.append(
        "<div class='chat-actions'>"
        "<a href='/chat?new=1'><button type='button'>New chat</button></a>"
        f"<form method='post' action='/chat/archive'>"
        f"<input type='hidden' name='chat_id' value='{_h(chat_id)}'>"
        "<button type='submit'>Archive chat</button>"
        "</form>"
        "</div>"
    )

    if not rows:
        body.append("<p>No messages yet.</p>")
    for row in rows:
        role = row.get("role") or "user"
        cls = "msg-assistant" if role == "assistant" else "msg-user"
        meta_str = _h(json.dumps(row.get("metadata") or {}, ensure_ascii=False))
        msg = (
            f"<div class='{cls}'><div><strong>{_h(role)}</strong> "
            f"<span class='ts'>{_h(str(row.get('occurred_at','')))}</span></div>"
            f"<div class='msg-body'>{_h(row.get('content') or '')}</div>"
        )
        if role == "assistant":
            iid = row.get("id") or ""
            msg += (
                "<div style='margin-top:8px'>"
                f"<form style='display:inline-block' method='post' action='/chat/feedback'>"
                f"<input type='hidden' name='chat_id' value='{_h(chat_id)}'>"
                f"<input type='hidden' name='interaction_id' value='{_h(iid)}'>"
                "<input type='hidden' name='vote' value='up'>"
                "<button type='submit'>👍 Approve</button></form>"
                "</div>"
                "<div style='margin-top:8px'>"
                f"<form method='post' action='/chat/feedback'>"
                f"<input type='hidden' name='chat_id' value='{_h(chat_id)}'>"
                f"<input type='hidden' name='interaction_id' value='{_h(iid)}'>"
                "<input type='hidden' name='vote' value='down'>"
                "<label>👎 Decline category</label>"
                "<select name='category'>"
                "<option value=''>--select--</option>"
                "<option value='accuracy'>accuracy</option>"
                "<option value='evidence'>evidence</option>"
                "<option value='relevance'>relevance</option>"
                "<option value='format'>format</option>"
                "<option value='tone'>tone</option>"
                "<option value='other'>other</option>"
                "</select>"
                "<label>What was wrong?</label>"
                "<textarea name='comment' rows='2' placeholder='optional details'></textarea>"
                "<button type='submit'>Submit decline feedback</button>"
                "</form>"
                "</div>"
            )
        msg += f"<details><summary>details</summary><pre>{meta_str}</pre></details>"
        msg += "</div>"
        body.append(msg)
    body.append(
        "<h3>Send message</h3>"
        "<form id='chat_form' method='post' action='/chat/send'>"
        f"<input type='hidden' name='chat_id' value='{_h(chat_id)}'>"
        "<textarea id='message_box' name='message' rows='3' placeholder='Type your message'></textarea>"
        "<button type='submit'>Send</button>"
        "</form>"
        "<script>"
        "(function(){"
        "var form=document.getElementById('chat_form');"
        "var box=document.getElementById('message_box');"
        "if(!form||!box){return;}"
        "box.addEventListener('keydown',function(ev){"
        "if(ev.key==='Enter' && !ev.shiftKey){ev.preventDefault(); form.requestSubmit();}"
        "});"
        "})();"
        "</script>"
        "</div></section></div>"
    )
    return HTMLResponse(layout("Chat", "".join(body)))


@app.post("/chat/send")
def chat_send(chat_id: str = Form(""), message: str = Form(...)) -> RedirectResponse:
    chat_id = (chat_id or "").strip() or new_chat_id()
    text_raw = message
    if not text_raw.strip():
        return RedirectResponse(url=f"/chat?chat_id={chat_id}", status_code=303)

    language_code = detect_message_language(text_raw)
    history_turns = load_chat_history_for_prompt(chat_id=chat_id, limit=10)
    pks_rows = load_pks_context(limit=6)
    evidence_rows = load_local_evidence_context(query=text_raw, limit=5)
    source_lines = build_human_sources_lines(language_code, pks_rows, evidence_rows)

    user_id = insert_interaction("user", text_raw, {"source": "ui", "chat_id": chat_id})

    if is_greeting_only(text_raw, language_code):
        answer = render_chat_default_output(greeting_clarifying_answer(language_code), language_code, text_raw, sources=source_lines)
        insert_interaction(
            "assistant",
            answer,
            {
                "source": "ui",
                "chat_id": chat_id,
                "model_adapter": "greeting-shortcut",
                "generation_path": "greeting_shortcut",
                "language": language_code,
                "related_user_interaction_id": user_id,
            },
        )
        return RedirectResponse(url=f"/chat?chat_id={chat_id}", status_code=303)

    followup_answer = resolve_followup_from_history(text_raw, history_turns, language_code)
    if followup_answer:
        answer = render_chat_default_output(followup_answer, language_code, text_raw, sources=source_lines)
        insert_interaction(
            "assistant",
            answer,
            {
                "source": "ui",
                "chat_id": chat_id,
                "model_adapter": "history-shortcut",
                "generation_path": "history_shortcut",
                "language": language_code,
                "related_user_interaction_id": user_id,
            },
        )
        return RedirectResponse(url=f"/chat?chat_id={chat_id}", status_code=303)

    model, adapter_error = select_chat_model_adapter()
    if is_daily_planning_request(text_raw):
        if adapter_error:
            plan_answer = (
                "A helyi modell nem elérhető. Kérlek indítsd el az Ollama szolgáltatást, majd próbáld újra."
                if language_code == "hu"
                else "Local model is unavailable. Start Ollama and try again."
            )
            assumptions = ["Feltételezés: helyi modell jelenleg nem elérhető."] if language_code == "hu" else ["Assumption: local model is currently unavailable."]
            actions = ["P0 [ ] Indítsd el az Ollama szolgáltatást.", "P1 [ ] Küldd újra a napi tervezési kérést."] if language_code == "hu" else ["P0 [ ] Start Ollama service.", "P1 [ ] Resend the daily planning request."]
        else:
            try:
                plan_answer, assumptions, actions = generate_planning_structured(
                    model=model,
                    language_code=language_code,
                    user_text=text_raw,
                    context={
                        "history": [{"role": x.get("role", ""), "content": (x.get("content") or "")[:140]} for x in history_turns[-6:]],
                        "pks": summarize_pks_for_model(pks_rows, limit=3),
                        "evidence": summarize_evidence_for_model(evidence_rows, limit=3),
                    },
                )
            except Exception:
                if language_code == "hu":
                    plan_answer = "Itt egy rövid, pragmatikus napi terv a mai napra."
                    assumptions = [
                        "Feltételezés: OFFLINE módban dolgozunk, webes forrás nélkül.",
                        "Feltételezés: nincs átadott naptár, fix meeting vagy határidő.",
                    ]
                    actions = [
                        "P0 [ ] Nevezd meg a mai egyetlen legfontosabb eredményt.",
                        "P0 [ ] Válassz legfeljebb 3 fókuszfeladatot a mai napra.",
                        "P1 [ ] Bontsd a 3 feladatot első konkrét lépésekre.",
                        "P1 [ ] Ütemezz 1 admin/kommunikációs tételt.",
                        "P1 [ ] Tervezz 1 pufferblokkot megszakításokra.",
                        "P2 [ ] Nap végén tarts 10 perces záróértékelést.",
                    ]
                else:
                    plan_answer = "Here is a short pragmatic plan for today."
                    assumptions = [
                        "Assumption: offline mode only, without web sources.",
                        "Assumption: no explicit calendar, fixed meetings, or deadlines were provided.",
                    ]
                    actions = [
                        "P0 [ ] Define one most important outcome for today.",
                        "P0 [ ] Pick up to 3 focus tasks.",
                        "P1 [ ] Break each task into a first concrete step.",
                        "P1 [ ] Schedule one admin/coordination item.",
                        "P1 [ ] Reserve one buffer block for interruptions.",
                        "P2 [ ] Run a 10-minute end-of-day review.",
                    ]

        answer = render_chat_default_output(
            plan_answer,
            language_code,
            text_raw,
            sources=source_lines,
            assumptions_override=assumptions,
            next_actions_override=actions,
        )
        if _has_forbidden_user_visible_markers(answer):
            if language_code == "hu":
                answer = render_chat_default_output(
                    "Rendszerhiba történt a válasz összeállításakor. Kérlek próbáld újra.",
                    language_code,
                    text_raw,
                    sources=source_lines,
                )
            else:
                answer = render_chat_default_output(
                    "A system error occurred while assembling the response. Please retry.",
                    language_code,
                    text_raw,
                    sources=source_lines,
                )
            insert_learning(
                kind="NegativeFeedback",
                confidence="High",
                details={
                    "vote": "down",
                    "category": "format",
                    "comment": "planning rendered output failed validator",
                    "ui_context": {"route": "/chat/send", "source": "validator"},
                },
                related_interaction_id=user_id,
            )
        insert_interaction(
            "assistant",
            answer,
            {
                "source": "ui",
                "chat_id": chat_id,
                "model_adapter": model.name if model is not None else "unavailable",
                "generation_path": "planning_structured",
                "language": language_code,
                "related_user_interaction_id": user_id,
            },
        )
        return RedirectResponse(url=f"/chat?chat_id={chat_id}", status_code=303)

    system_prompt = build_system_prompt()
    task_prompt = build_task_prompt(
        user_text=text_raw,
        connectivity="OFFLINE",
        retrieved_context={
            "source": "ui.chat",
            "recent_history": [{"role": (x.get("role") or ""), "content": (x.get("content") or "")[:220]} for x in history_turns[-6:]],
            "pks_approved": summarize_pks_for_model(pks_rows, limit=4),
            "local_evidence_top": summarize_evidence_for_model(evidence_rows, limit=4),
        },
    )
    task_prompt += (
        "\nChat generation requirements:\n"
        f"- Respond in {language_name(language_code)}.\n"
        "- Keep the answer factual and useful.\n"
        "- Do not repeat the prompt template or system instructions.\n"
        "- Answer the user request directly.\n"
    )
    if adapter_error:
        raw_answer = localized_model_error(language_code, adapter_error)
    else:
        try:
            raw_answer = model.generate(system_prompt=system_prompt, task_prompt=task_prompt).strip()
        except Exception as exc:
            raw_answer = localized_model_error(language_code, str(exc))
    if not raw_answer:
        raw_answer = localized_model_error(language_code, "empty response")

    clean_answer, removed_ratio = _sanitize_with_stats(raw_answer)
    if model is not None and _needs_repair(raw_answer, clean_answer, removed_ratio):
        try:
            clean_answer = _repair_assistant_output(model, language_code, text_raw, raw_answer)
        except Exception:
            clean_answer = localized_model_error(language_code, "unsafe model output removed")
    if model is not None and language_code == "hu" and not _looks_hungarian(clean_answer):
        try:
            clean_answer = _repair_assistant_output(model, language_code, text_raw, clean_answer)
        except Exception:
            clean_answer = "Rendszerhiba történt a válasz összeállításakor. Kérlek próbáld újra."

    clean_answer = sanitize_assistant_output(clean_answer)
    if _has_forbidden_user_visible_markers(clean_answer) and model is not None:
        try:
            clean_answer = _repair_assistant_output_idsafe(model, language_code, text_raw, clean_answer)
        except Exception:
            pass
    if _has_forbidden_user_visible_markers(clean_answer):
        if language_code == "hu":
            clean_answer = "Rendszerhiba történt a válasz összeállításakor. Kérlek próbáld újra."
        else:
            clean_answer = "I cannot produce a safe user-visible answer in this form. Please restate your request briefly."
        insert_learning(
            kind="NegativeFeedback",
            confidence="High",
            details={
                "vote": "down",
                "category": "format",
                "comment": "assistant output rejected by user-visible validator",
                "ui_context": {"route": "/chat/send", "source": "validator"},
            },
            related_interaction_id=user_id,
        )
    if not clean_answer:
        clean_answer = localized_model_error(language_code, "empty sanitized output")
    answer = render_chat_default_output(clean_answer, language_code, text_raw, sources=source_lines)

    insert_interaction(
        "assistant",
        answer,
        {
            "source": "ui",
            "chat_id": chat_id,
            "model_adapter": model.name if model is not None else "unavailable",
            "generation_path": "standard",
            "language": language_code,
            "related_user_interaction_id": user_id,
        },
    )
    return RedirectResponse(url=f"/chat?chat_id={chat_id}", status_code=303)


@app.post("/chat/feedback")
def chat_feedback(
    chat_id: str = Form(""),
    interaction_id: str = Form(...),
    vote: str = Form(...),
    category: str = Form(""),
    comment: str = Form(""),
):
    if not UUID_RE.match(interaction_id):
        return HTMLResponse(layout("Error", "<div class='card'><h2>Invalid interaction id</h2></div>"), status_code=400)
    role = psql(
        "SELECT role FROM interaction_events "
        f"WHERE id='{_esc_sql(interaction_id)}' LIMIT 1;"
    ).strip()
    if role != "assistant":
        return HTMLResponse(layout("Error", "<div class='card'><h2>Feedback requires assistant message id</h2></div>"), status_code=400)

    v = vote.strip().lower()
    c = category.strip().lower()
    msg = comment.strip()
    if v == "down" and not c and not msg:
        return HTMLResponse(
            layout("Error", "<div class='card'><h2>Downvote requires category or comment</h2></div>"),
            status_code=400,
        )

    if v == "up":
        kind = "PositiveFeedback"
        confidence = "High"
    else:
        kind = "NegativeFeedback"
        confidence = "Medium"
    details = {
        "vote": v,
        "category": c or "other",
        "comment": msg,
        "ui_context": {"route": "/chat", "chat_id": chat_id, "source": "ui"},
    }
    insert_learning(kind=kind, confidence=confidence, details=details, related_interaction_id=interaction_id)
    return RedirectResponse(url=f"/chat?chat_id={chat_id}", status_code=303)


@app.get("/upload", response_class=HTMLResponse)
def upload_page() -> HTMLResponse:
    inner = (
        "<div class='card'><h2>Upload artefact</h2>"
        "<form method='post' action='/upload' enctype='multipart/form-data'>"
        "<input type='file' name='file' required>"
        "<button type='submit'>Upload</button>"
        "</form></div>"
    )
    return HTMLResponse(layout("Upload", inner))


@app.post("/upload", response_class=HTMLResponse)
async def upload(file: UploadFile = File(...)) -> HTMLResponse:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    original = Path(file.filename or "upload.bin").name
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    saved_name = f"{stamp}__{original}"
    target = UPLOAD_DIR / saved_name

    data = await file.read()
    target.write_bytes(data)

    artefact_id = str(uuid.uuid4())
    sha = hashlib.sha256(data).hexdigest()
    size = len(data)
    media_type = file.content_type or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    suffix = target.suffix.lower()

    parsed = suffix in {".txt", ".md"}
    parse_status = "parsed" if parsed else "unparsed"
    metadata = {
        "source": "ui.upload",
        "path": str(target),
        "size_bytes": size,
        "sensitivity": "Private",
        "provenance": "LocalDoc",
        "parse_status": parse_status,
    }
    psql(
        "INSERT INTO artefacts (id, kind, uri, title, media_type, sha256, metadata) "
        f"VALUES ('{artefact_id}', 'file', '{_esc_sql(str(target))}', '{_esc_sql(original)}', "
        f"'{_esc_sql(media_type)}', '{sha}', '{_esc_sql(json.dumps(metadata, ensure_ascii=False))}'::jsonb);"
    )
    audit("upload", "artefact", artefact_id, {"path": str(target), "parse_status": parse_status, "size": size})

    chunks_created = 0
    if parsed:
        text = data.decode("utf-8", errors="ignore")
        chunks = chunk_text(text)
        adapter = get_embeddings_adapter()
        vectors = adapter.embed(chunks) if chunks else []
        for idx, chunk in enumerate(chunks):
            emb_id = str(uuid.uuid4())
            chunk_id = f"{artefact_id}:{idx}"
            emb_sql = _esc_sql(vector_sql_literal(vectors[idx]))
            cmeta = {
                "source": "ui.upload",
                "index": idx,
                "path": str(target),
                "embedder": adapter.name,
                "embed_dim": adapter.dimension,
            }
            psql(
                "INSERT INTO embeddings (id, artefact_id, chunk_id, content, embedding, metadata) "
                f"VALUES ('{emb_id}', '{artefact_id}', '{_esc_sql(chunk_id)}', '{_esc_sql(chunk)}', "
                f"'{emb_sql}'::vector, '{_esc_sql(json.dumps(cmeta, ensure_ascii=False))}'::jsonb);"
            )
            chunks_created += 1

    inner = (
        "<div class='card'><h2>Upload successful</h2>"
        f"<p><strong>artefact_id:</strong> {_h(artefact_id)}</p>"
        f"<p><strong>file:</strong> {_h(str(target))}</p>"
        f"<p><strong>sha256:</strong> {_h(sha)}</p>"
        f"<p><strong>parse_status:</strong> {_h(parse_status)}</p>"
        f"<p><strong>chunks_created:</strong> {_h(str(chunks_created))}</p>"
        "</div>"
    )
    return HTMLResponse(layout("Upload Result", inner))


@app.get("/search", response_class=HTMLResponse)
def search(query: str = "", limit: int = 10) -> HTMLResponse:
    q = query.strip()
    results = []
    if q:
        payload = search_runtime(q, limit=max(1, min(30, int(limit))), allow_pending=False)
        results = payload.get("results", [])

    rows = [
        "<div class='card'><h2>Search</h2>"
        "<form method='get' action='/search'>"
        f"<input type='text' name='query' value='{_h(q)}' placeholder='Search local evidence'>"
        f"<input type='text' name='limit' value='{_h(str(limit))}' placeholder='limit'>"
        "<button type='submit'>Search</button>"
        "</form></div>"
    ]
    if q and not results:
        rows.append("<div class='card'><p>No local matches.</p></div>")
    for row in results:
        aid = row.get("artefact_id") or ""
        checksum = ""
        path = row.get("artefact_uri") or ""
        if aid:
            checksum = psql(f"SELECT COALESCE(sha256,'') FROM artefacts WHERE id='{_esc_sql(aid)}' LIMIT 1;").strip()
        rows.append(
            "<div class='card'>"
            f"<div><strong>{_h(str(row.get('citation','')))}</strong> score={_h(str(row.get('score','')))}</div>"
            f"<div>{_h(str(row.get('excerpt','')))}</div>"
            f"<div style='color:#6b7280'>artefact_id={_h(str(aid))} provenance={_h(str(row.get('provenance','')))}</div>"
            f"<div style='color:#6b7280'>path={_h(str(path))} checksum={_h(str(checksum))}</div>"
            "</div>"
        )
    return HTMLResponse(layout("Search", "".join(rows)))


@app.get("/interactions", response_class=HTMLResponse)
def interactions() -> HTMLResponse:
    rows = psql("SELECT occurred_at, role, content, id FROM interaction_events ORDER BY occurred_at DESC LIMIT 100;")
    return HTMLResponse(layout("Interactions", f"<div class='card'><h2>Interactions</h2><pre>{_h(rows)}</pre></div>"))


@app.get("/learning", response_class=HTMLResponse)
def learning() -> HTMLResponse:
    rows = psql("SELECT occurred_at, kind, confidence, details, related_interaction_id FROM learning_events ORDER BY occurred_at DESC LIMIT 100;")
    return HTMLResponse(layout("Learning", f"<div class='card'><h2>Learning</h2><pre>{_h(rows)}</pre></div>"))


@app.get("/pks/pending", response_class=HTMLResponse)
def pks_pending() -> HTMLResponse:
    rows = psql("SELECT id, module, status, title, updated_at FROM pks_records WHERE status='Pending' ORDER BY updated_at DESC LIMIT 200;")
    inner = "<div class='card'><h2>PKS Pending</h2>"
    inner += "<table style='width:100%; border-collapse:collapse'><tr><th style='text-align:left; padding:6px'>Module</th><th style='text-align:left; padding:6px'>Title</th><th style='text-align:left; padding:6px'>Updated</th><th style='text-align:left; padding:6px'>Actions</th></tr>"
    for line in rows.splitlines():
        parts = line.split("|")
        if len(parts) < 5:
            continue
        rid, module, _status, title, updated_at = parts[0], parts[1], parts[2], parts[3], parts[4]
        inner += "<tr>"
        inner += f"<td style='padding:6px'>{_h(module)}</td>"
        inner += f"<td style='padding:6px'><div><a href='/pks/{_h(rid)}'>{_h(title)}</a></div><div style='color:#6b7280; font-size:12px'>{_h(rid)}</div></td>"
        inner += f"<td style='padding:6px; color:#6b7280'>{_h(updated_at)}</td>"
        inner += "<td style='padding:6px'>"
        inner += f"<form style='display:inline-block; margin-right:8px' method='post' action='/pks/approve'><input type='hidden' name='id' value='{_h(rid)}'><input style='margin-right:6px' name='reason' placeholder='reason (optional)'><button>Approve</button></form>"
        inner += f"<form style='display:inline-block' method='post' action='/pks/deprecate'><input type='hidden' name='id' value='{_h(rid)}'><input style='margin-right:6px' name='reason' placeholder='reason (optional)'><button>Deprecate</button></form>"
        inner += "</td></tr>"
    inner += "</table></div>"
    return HTMLResponse(layout("PKS Pending", inner))


@app.get("/pks/all", response_class=HTMLResponse)
def pks_all() -> HTMLResponse:
    rows = psql("SELECT id, module, status, title, updated_at FROM pks_records ORDER BY updated_at DESC LIMIT 300;")
    lines = []
    for line in rows.splitlines():
        parts = line.split("|")
        if len(parts) < 5:
            continue
        rid, module, status, title, updated_at = parts[0], parts[1], parts[2], parts[3], parts[4]
        lines.append(
            f"<tr><td style='padding:6px'><a href='/pks/{_h(rid)}'>{_h(rid)}</a></td>"
            f"<td style='padding:6px'>{_h(module)}</td><td style='padding:6px'>{_h(status)}</td>"
            f"<td style='padding:6px'>{_h(title)}</td><td style='padding:6px'>{_h(updated_at)}</td></tr>"
        )
    inner = "<div class='card'><h2>PKS</h2><table style='width:100%; border-collapse:collapse'><tr><th style='text-align:left; padding:6px'>ID</th><th style='text-align:left; padding:6px'>Module</th><th style='text-align:left; padding:6px'>Status</th><th style='text-align:left; padding:6px'>Title</th><th style='text-align:left; padding:6px'>Updated</th></tr>"
    inner += "".join(lines) + "</table></div>"
    return HTMLResponse(layout("PKS", inner))


@app.post("/pks/approve")
def approve(id: str = Form(...), reason: str = Form(default="")):
    if not UUID_RE.match(id):
        return HTMLResponse(layout("Error", "<div class='card'><h2>Invalid UUID</h2></div>"), status_code=400)
    psql(f"UPDATE pks_records SET status='Approved', updated_at=now() WHERE id='{_esc_sql(id)}';")
    details = {"status": "Approved"}
    if reason.strip():
        details["reason"] = reason.strip()
    audit("approve", "pks_record", id, details)
    return RedirectResponse(url="/pks/pending", status_code=303)


@app.post("/pks/deprecate")
def deprecate(id: str = Form(...), reason: str = Form(default="")):
    if not UUID_RE.match(id):
        return HTMLResponse(layout("Error", "<div class='card'><h2>Invalid UUID</h2></div>"), status_code=400)
    psql(f"UPDATE pks_records SET status='Deprecated', updated_at=now() WHERE id='{_esc_sql(id)}';")
    details = {"status": "Deprecated"}
    if reason.strip():
        details["reason"] = reason.strip()
    audit("deprecate", "pks_record", id, details)
    return RedirectResponse(url="/pks/pending", status_code=303)


@app.get("/pks/{rid}", response_class=HTMLResponse)
def pks_detail(rid: str) -> HTMLResponse:
    if not UUID_RE.match(rid):
        return HTMLResponse(layout("Error", "<div class='card'><h2>Invalid UUID</h2></div>"), status_code=400)
    rec = psql(
        "SELECT id, module, status, title, body, provenance, confidence, scope, created_at, updated_at "
        f"FROM pks_records WHERE id='{_esc_sql(rid)}' LIMIT 1;"
    )
    if not rec.strip():
        return HTMLResponse(layout("Not Found", "<div class='card'><h2>Record not found</h2></div>"), status_code=404)
    parts = rec.split("|")
    if len(parts) < 10:
        return HTMLResponse(layout("Error", "<div class='card'><h2>Unexpected record payload</h2></div>"), status_code=500)
    body = (
        "<div class='card'>"
        f"<h2>{_h(parts[3])}</h2>"
        f"<p><strong>ID:</strong> {_h(parts[0])}</p>"
        f"<p><strong>Module:</strong> {_h(parts[1])} | <strong>Status:</strong> {_h(parts[2])}</p>"
        f"<p><strong>Provenance:</strong> {_h(parts[5])} | <strong>Confidence:</strong> {_h(parts[6])} | <strong>Scope:</strong> {_h(parts[7])}</p>"
        f"<p><strong>Created:</strong> {_h(parts[8])} | <strong>Updated:</strong> {_h(parts[9])}</p>"
        f"<h3>Body</h3><pre>{_h(parts[4])}</pre>"
        "<div style='margin-top:12px'>"
        f"<form style='display:inline-block; margin-right:8px' method='post' action='/pks/approve'><input type='hidden' name='id' value='{_h(rid)}'><input style='margin-right:6px' name='reason' placeholder='reason (optional)'><button>Approve</button></form>"
        f"<form style='display:inline-block' method='post' action='/pks/deprecate'><input type='hidden' name='id' value='{_h(rid)}'><input style='margin-right:6px' name='reason' placeholder='reason (optional)'><button>Deprecate</button></form>"
        "</div>"
        "</div>"
    )
    return HTMLResponse(layout("PKS Detail", body))


@app.get("/export.json")
def export_json() -> JSONResponse:
    def q(sql: str) -> list[dict]:
        cmd = [
            "docker",
            "exec",
            "-i",
            CID,
            "psql",
            "-U",
            "hatori",
            "-d",
            "hatori",
            "-t",
            "-A",
            "-c",
            f"SELECT COALESCE(json_agg(t), '[]'::json) FROM ({sql}) t;",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return []
        out = (r.stdout or "").strip()
        return json.loads(out) if out else []

    data = {
        "pks_records": q("SELECT * FROM pks_records ORDER BY updated_at DESC LIMIT 2000"),
        "interaction_events": q("SELECT * FROM interaction_events ORDER BY occurred_at DESC LIMIT 2000"),
        "learning_events": q("SELECT * FROM learning_events ORDER BY occurred_at DESC LIMIT 2000"),
        "audit_events": q("SELECT * FROM audit_events ORDER BY occurred_at DESC LIMIT 2000"),
    }
    return JSONResponse(data)


@app.post("/export/disk")
def export_disk() -> RedirectResponse:
    payload = export_json().body.decode("utf-8")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"export-{stamp}.json"
    path = EXPORT_DIR / filename
    path.write_text(payload, encoding="utf-8")

    artefact_id = psql("SELECT gen_random_uuid();").strip()
    metadata = _esc_sql(json.dumps({"source": "ui", "export": "snapshot"}, ensure_ascii=False))
    uri = _esc_sql(str(path))
    title = _esc_sql(filename)
    psql(
        "INSERT INTO artefacts (id, kind, uri, title, media_type, metadata) "
        f"VALUES ('{artefact_id}', 'export', '{uri}', '{title}', 'application/json', '{metadata}'::jsonb);"
    )
    audit("export_snapshot", "artefact", artefact_id, {"uri": str(path)})
    return RedirectResponse(url="/pks/all", status_code=303)
