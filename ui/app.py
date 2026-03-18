import hashlib
import html
import json
import mimetypes
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
import re
from typing import Any
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
from hatori.model import get_task_model_adapter
from hatori.model import OllamaAdapter
from hatori.model import prefer_ollama_if_available
from hatori.prompts import build_system_prompt
from hatori.prompts import build_task_prompt
from hatori.cli import search_runtime
from hatori.cli import connectivity_state

CID = os.environ.get("CID", "hatori-pg")
UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
UUID_ANY_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)
ROOT_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT_DIR / "VERSION"
EXPORT_DIR = ROOT_DIR / "artefacts" / "exports"
UPLOAD_DIR = ROOT_DIR / "artefacts" / "uploads"


def _app_version() -> str:
    """Read app version from VERSION file for UI display."""
    try:
        if VERSION_FILE.is_file():
            return VERSION_FILE.read_text(encoding="utf-8").strip() or "0.0.0"
    except Exception:
        pass
    return "0.0.0"

LOCALES_PATH = Path(__file__).resolve().parent / "locales.json"
try:
    with open(LOCALES_PATH, "r", encoding="utf-8") as f:
        _LOCALES = json.load(f)
except Exception:
    _LOCALES = {}

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


def _jsonb_sql_literal(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False)
    tag = f"json_{uuid.uuid4().hex}"
    return f"${tag}${raw}${tag}$::jsonb"


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
    sql = (
        "INSERT INTO interaction_events (id, role, content, metadata) "
        f"VALUES ('{iid}', '{_esc_sql(role)}', '{_esc_sql(content)}', {_jsonb_sql_literal(metadata)});"
    )
    psql(sql)
    return iid


def insert_learning(kind: str, confidence: str, details: dict, related_interaction_id: str) -> str:
    lid = str(uuid.uuid4())
    sql = (
        "INSERT INTO learning_events (id, kind, confidence, details, related_interaction_id) "
        f"VALUES ('{lid}', '{_esc_sql(kind)}', '{_esc_sql(confidence)}', {_jsonb_sql_literal(details)}, '{_esc_sql(related_interaction_id)}');"
    )
    psql(sql)
    return lid


def audit(action: str, target_type: str, target_id: str, details: dict) -> None:
    sql = (
        "INSERT INTO audit_events (id, actor, action, target_type, target_id, details) "
        f"VALUES (gen_random_uuid(), 'ui', '{_esc_sql(action)}', '{_esc_sql(target_type)}', '{_esc_sql(target_id)}', {_jsonb_sql_literal(details)});"
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


def summarize_recent_learning_for_model(limit: int = 15) -> dict[str, Any]:
    """Load recent learning_events and return a short summary for prompt context (feedback→behavior)."""
    rows = psql_json(
        "SELECT kind, confidence, details, occurred_at "
        "FROM learning_events "
        "ORDER BY occurred_at DESC "
        f"LIMIT {int(limit)}"
    )
    counts: dict[str, int] = {}
    last_negative_comment: str = ""
    last_positive_note: str = ""
    for row in rows:
        k = (row.get("kind") or "").strip()
        if k:
            counts[k] = counts.get(k, 0) + 1
        details = row.get("details") or {}
        if isinstance(details, dict):
            comment = (details.get("comment") or details.get("edit_reason") or "").strip()[:200]
            if k == "NegativeFeedback" and comment and not last_negative_comment:
                last_negative_comment = comment
            if k == "PositiveFeedback" and not last_positive_note:
                last_positive_note = "User approved this style." if not comment else comment[:120]
    summary_parts = [f"{k}: {v}" for k, v in sorted(counts.items())]
    return {
        "counts": counts,
        "summary": "Recent feedback: " + "; ".join(summary_parts) if summary_parts else "No recent feedback.",
        "last_negative_comment": last_negative_comment or "",
        "last_positive_note": last_positive_note or "",
    }


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


def is_greeting_only(text: str, language_code: str) -> bool:
    clean = re.sub(r"[^\w\s]", "", (text or "").lower().strip())
    words = clean.split()
    if not words:
        return False
    if len(words) > 4:
        return False
    greetings = {"hi", "hello", "hey", "szia", "szió", "szép", "reggelt", "napot", "estét", "jó", "salut", "bonjour", "hallo", "hola"}
    return all(w in greetings for w in words)


def greeting_clarifying_answer(language_code: str) -> str:
    if language_code == "hu":
        return "Szia! Miben segíthetek pontosan ma?"
    if language_code == "ro":
        return "Salut! Cu ce te pot ajuta exact astăzi?"
    if language_code == "es":
        return "¡Hola! ¿En qué puedo ayudarte exactamente hoy?"
    if language_code == "fr":
        return "Bonjour ! Comment puis-je vous aider exactement aujourd'hui ?"
    if language_code == "de":
        return "Hallo! Wobei genau kann ich dir heute helfen?"
    return "Hello! How exactly can I help you today?"


def localized_model_error(code: str, err: str) -> str:
    start_cmd = os.environ.get("HATORI_OLLAMA_START_CMD", "starting your local inference engine")
    locale_dict = _LOCALES.get(code, _LOCALES.get("en", {}))
    base_template = locale_dict.get(
        "model_error",
        "Local model is temporarily unavailable. Please retry in a few seconds. If the model is not running, try '{start_cmd}'."
    )
    base = base_template.replace("{start_cmd}", start_cmd)
    return f"{base} (Model Error: {err})"


def is_weather_request(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return bool(
        re.search(
            r"\b(weather|forecast|temperature|temp|rain|wind|humidity|idojaras|homerseklet|vremea|meteo)\b",
            t,
        )
    )


def localized_weather_offline_fallback(code: str, user_text: str) -> str:
    city_match = re.search(r"\b(?:in|for)\s+([A-Za-z][A-Za-z .'-]{1,40})\b", user_text, flags=re.IGNORECASE)
    city = (city_match.group(1).strip() if city_match else "").rstrip("?.!,")
    place = city or "that location"
    if code == "hu":
        return f"Most nem erek el elo idojarasi adatot {place} teruletre. Nyisd meg az Apple Weather vagy a weather.com oldalt, es irj vissza a hofok/szel/paratartalom adataival; azokbol azonnal adok rovid ertelmezest."
    return f"I cannot fetch live weather data for {place} right now. Please check Apple Weather or weather.com and share temperature/wind/humidity, and I will summarize it immediately."


def is_online_search_request(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return bool(
        re.search(
            r"\b(weather|forecast|latest|today|news|current|price|stock|who is|what is|search|look up|find online|internet)\b",
            t,
        )
    )


def should_route_online_search(text: str, conn_state: str) -> bool:
    if conn_state == "OFFLINE":
        return False
    mode = (os.environ.get("HATORI_ONLINE_ROUTE_MODE") or "auto").strip().lower()
    if mode == "off":
        return False
    if mode == "keyword":
        return is_online_search_request(text)
    # auto: route most natural-language questions via online retrieval when internet mode is on.
    clean = (text or "").strip()
    if not clean:
        return False
    if len(clean) >= 12:
        return True
    return "?" in clean


def _searxng_base_url() -> str:
    return (os.environ.get("HATORI_SEARXNG_URL") or "http://127.0.0.1:8888").strip().rstrip("/")


def _searxng_search(query: str, limit: int = 5) -> list[dict[str, str]]:
    engines = (os.environ.get("HATORI_SEARXNG_ENGINES") or "wikipedia,startpage").strip()
    endpoint = _searxng_base_url() + "/search?" + urllib.parse.urlencode(
        {
            "q": query,
            "format": "json",
            "language": "en-US",
            "safesearch": "0",
            "engines": engines,
        }
    )
    req = urllib.request.Request(
        endpoint,
        headers={
            "User-Agent": "hatori/1.0",
            "Accept": "application/json",
            "X-Forwarded-For": "127.0.0.1",
            "X-Real-IP": "127.0.0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=6) as resp:
        raw = resp.read()
    payload = json.loads(raw.decode("utf-8", errors="ignore"))
    results = payload.get("results") or []
    hits: list[dict[str, str]] = []
    for item in results:
        if len(hits) >= limit:
            break
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("content") or "").strip()
        url = str(item.get("url") or "").strip()
        if title or snippet:
            hits.append({"title": title or "Result", "snippet": snippet, "url": url})
    return hits


def online_search_snippets(query: str, limit: int = 5) -> list[dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []
    # Primary online retrieval backend: SearXNG (self-hosted or local gateway).
    try:
        hits = _searxng_search(q, limit=limit)
        if hits:
            return hits[:limit]
    except Exception:
        pass
    # Fallbacks keep online mode usable even if SearXNG is temporarily unavailable.
    endpoint = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
        {
            "q": q,
            "format": "json",
            "no_html": "1",
            "no_redirect": "1",
            "skip_disambig": "1",
        }
    )
    req = urllib.request.Request(endpoint, headers={"User-Agent": "hatori/1.0"})
    with urllib.request.urlopen(req, timeout=6) as resp:
        raw = resp.read()
    payload = json.loads(raw.decode("utf-8", errors="ignore"))
    hits: list[dict[str, str]] = []
    abstract = (payload.get("AbstractText") or "").strip()
    abstract_url = (payload.get("AbstractURL") or "").strip()
    if abstract:
        hits.append({"title": "Summary", "snippet": abstract, "url": abstract_url})
    for item in payload.get("RelatedTopics") or []:
        if len(hits) >= limit:
            break
        text = (item.get("Text") or "").strip() if isinstance(item, dict) else ""
        url = (item.get("FirstURL") or "").strip() if isinstance(item, dict) else ""
        if text:
            title = text.split(" - ", 1)[0][:120]
            hits.append({"title": title, "snippet": text, "url": url})
    if hits:
        return hits[:limit]
    wiki_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "opensearch",
            "search": q,
            "limit": str(max(1, min(8, int(limit)))),
            "namespace": "0",
            "format": "json",
        }
    )
    wiki_req = urllib.request.Request(wiki_url, headers={"User-Agent": "hatori/1.0"})
    with urllib.request.urlopen(wiki_req, timeout=6) as resp:
        wiki_raw = resp.read()
    arr = json.loads(wiki_raw.decode("utf-8", errors="ignore"))
    if isinstance(arr, list) and len(arr) >= 4:
        titles = arr[1] if isinstance(arr[1], list) else []
        descs = arr[2] if isinstance(arr[2], list) else []
        urls = arr[3] if isinstance(arr[3], list) else []
        for i, title in enumerate(titles):
            if len(hits) >= limit:
                break
            snippet = str(descs[i]) if i < len(descs) else ""
            url = str(urls[i]) if i < len(urls) else ""
            hits.append({"title": str(title), "snippet": snippet, "url": url})
    return hits[:limit]


def _extract_weather_location(user_text: str) -> str:
    txt = (user_text or "").strip()
    for pat in [r"\b(?:in|for)\s+([A-Za-z][A-Za-z .'-]{1,40})\b", r"\b(?:at)\s+([A-Za-z][A-Za-z .'-]{1,40})\b"]:
        m = re.search(pat, txt, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip("?.!,")
    # Hungarian city suffix handling without hardcoding specific questions.
    words = re.findall(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű'-]+", txt)
    stopwords = {
        "milyen", "mi", "mennyi", "hany", "hány", "most", "ido", "idő", "van", "lesz",
        "hol", "szel", "szél", "fok", "fokos", "es", "és", "a", "az", "itt", "ott",
        "ma", "holnap", "tegnap", "kint", "kinn",
    }
    suffixes = ("ban", "ben", "rol", "ról", "nal", "nál", "tol", "tól", "ba", "be", "on", "en", "ön")
    candidates: list[str] = []
    for w in words:
        raw = w.strip("'-").lower()
        if len(raw) < 3:
            continue
        if raw in stopwords:
            continue
        stem = raw
        for sfx in suffixes:
            if stem.endswith(sfx) and len(stem) - len(sfx) >= 3:
                stem = stem[: -len(sfx)]
                break
        if stem and stem not in stopwords:
            candidates.append(stem)
    if candidates:
        return candidates[-1]
    return ""


def fetch_live_weather(location: str) -> dict[str, str]:
    loc = (location or "").strip()
    if not loc:
        return {}
    geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({"name": loc, "count": "1", "language": "en", "format": "json"})
    geo_req = urllib.request.Request(geo_url, headers={"User-Agent": "hatori/1.0"})
    with urllib.request.urlopen(geo_req, timeout=8) as resp:
        geo_raw = resp.read()
    geo_payload = json.loads(geo_raw.decode("utf-8", errors="ignore"))
    results = geo_payload.get("results") or []
    if not results or not isinstance(results[0], dict):
        return {}
    lat = results[0].get("latitude")
    lon = results[0].get("longitude")
    name = str(results[0].get("name") or loc).strip()
    country = str(results[0].get("country") or "").strip()
    place = f"{name}, {country}".strip().strip(",")
    if lat is None or lon is None:
        return {}
    wx_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
        {
            "latitude": str(lat),
            "longitude": str(lon),
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            "wind_speed_unit": "kmh",
            "timezone": "auto",
        }
    )
    wx_req = urllib.request.Request(wx_url, headers={"User-Agent": "hatori/1.0"})
    with urllib.request.urlopen(wx_req, timeout=8) as resp:
        wx_raw = resp.read()
    wx_payload = json.loads(wx_raw.decode("utf-8", errors="ignore"))
    cur = wx_payload.get("current") or {}
    if not isinstance(cur, dict):
        return {}
    code = str(cur.get("weather_code") or "").strip()
    code_map = {
        "0": "Clear sky",
        "1": "Mainly clear",
        "2": "Partly cloudy",
        "3": "Overcast",
        "45": "Fog",
        "48": "Rime fog",
        "51": "Light drizzle",
        "53": "Drizzle",
        "55": "Dense drizzle",
        "61": "Slight rain",
        "63": "Rain",
        "65": "Heavy rain",
        "71": "Slight snow",
        "73": "Snow",
        "75": "Heavy snow",
        "95": "Thunderstorm",
    }
    desc = ""
    if code:
        desc = code_map.get(code, f"Weather code {code}")
    return {
        "location": place or loc,
        "temp_c": str(cur.get("temperature_2m") or "").strip(),
        "feels_c": str(cur.get("temperature_2m") or "").strip(),
        "humidity": str(cur.get("relative_humidity_2m") or "").strip(),
        "wind_kmph": str(cur.get("wind_speed_10m") or "").strip(),
        "desc": desc,
    }









def build_online_context_block(hits: list[dict[str, str]]) -> str:
    if not hits:
        return "No online snippets available."
    lines = []
    for i, h in enumerate(hits[:6], start=1):
        title = (h.get("title") or "").strip()
        snippet = (h.get("snippet") or "").strip()
        url = (h.get("url") or "").strip()
        lines.append(f"[{i}] title={title}\n[{i}] snippet={snippet}\n[{i}] url={url}")
    return "\n".join(lines)


def online_synthesis_mode() -> str:
    mode = (os.environ.get("HATORI_ONLINE_SYNTHESIS_MODE") or "direct").strip().lower()
    if mode in {"direct", "llm"}:
        return mode
    return "direct"


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
    "verification ladder",
    "no memory changes",
    "connectivity state",
    "i am {hatori}",
    "i am hatori",
    "classify this as a daily task",
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
    "verification ladder",
    "no memory changes",
    "connectivity state",
    "i am {hatori}",
    "i am hatori",
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


def select_chat_model_adapter(task: str = "reply_write"):
    adapter, adapter_error, _route_meta = get_task_model_adapter(task)
    return adapter, adapter_error


def _extract_json_object_lenient(raw: str) -> dict | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def build_drafter_context_pack(user_text: str, language_code: str, history_turns: list[dict], pks_rows: list[dict], evidence_rows: list[dict]) -> dict:
    model, err = select_chat_model_adapter(task="context_pack")
    if model is None or err:
        return {}

    compact_history = [
        {"role": x.get("role", ""), "content": (x.get("content") or "")[:160]}
        for x in history_turns[-6:]
    ]
    prompt = (
        f"Return STRICT JSON only in {language_name(language_code)}. No markdown.\n"
        "Schema:\n"
        '{"intent":"string","constraints":["string"],"retrieval_queries":["string"],"response_outline":["string"]}\n'
        "Rules:\n"
        "- Keep intent short.\n"
        "- 1-4 constraints.\n"
        "- 1-3 retrieval_queries.\n"
        "- 2-5 response_outline bullets.\n"
        f"User message: {user_text}\n"
        f"History: {json.dumps(compact_history, ensure_ascii=False)}\n"
        f"PKS: {json.dumps(summarize_pks_for_model(pks_rows, limit=3), ensure_ascii=False)}\n"
        f"Evidence: {json.dumps(summarize_evidence_for_model(evidence_rows, limit=3), ensure_ascii=False)}\n"
    )
    try:
        raw = model.generate(system_prompt="Fast internal planner.", task_prompt=prompt)
        parsed = _extract_json_object_lenient(raw)
        if not parsed:
            return {}
        return {
            "intent": str(parsed.get("intent") or "").strip()[:120],
            "constraints": [str(x).strip()[:160] for x in (parsed.get("constraints") or []) if str(x).strip()][:4],
            "retrieval_queries": [str(x).strip()[:120] for x in (parsed.get("retrieval_queries") or []) if str(x).strip()][:3],
            "response_outline": [str(x).strip()[:200] for x in (parsed.get("response_outline") or []) if str(x).strip()][:5],
        }
    except Exception:
        return {}


def is_daily_planning_request(text: str) -> bool:
    lowered = (text or "").lower().strip()
    if not lowered:
        return False

    direct_patterns = [
        r"\bdaily\s+plan\b",
        r"\bweekly\s+plan\b",
        r"\bplan\s+my\s+day\b",
        r"\bplanning\b",
        r"\bnapi\s+terv\w*\b",
        r"\bheti\s+terv\w*\b",
        r"\btervez\w*\b",
        r"\bütemez\w*\b",
        r"\bpriorit[aá]s\w*\b",
        r"\bteend[oő]\w*\b",
    ]
    if any(re.search(pat, lowered) for pat in direct_patterns):
        return True

    has_today_marker = bool(re.search(r"\b(ma|mai|today)\b", lowered))
    has_task_marker = bool(re.search(r"\b(feladat\w*|tasks?|priorit(?:y|ies)|priorit[aá]s\w*)\b", lowered))
    return has_today_marker and has_task_marker


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
    bad_chars = ["±", "\x00"]
    answer_has_bad_chars = any(ch in answer for ch in bad_chars)
    if answer_has_bad_chars or len(answer) < 20:
        answer = ""
    assumptions = [x for x in assumptions if len(x) >= 12 and not any(ch in x for ch in bad_chars)]
    actions = [x for x in actions if len(x.strip()) >= 12 and not any(ch in x for ch in bad_chars)]

    # No hardcoded plan content: reject empty or invalid model output so caller can show retry.
    if not answer:
        raise ValueError("empty or invalid plan answer from model")

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

    # No padding with hardcoded actions; use only model output.
    normalized = normalized[:8]
    return answer, assumptions[:6], normalized


def generate_planning_structured(model, language_code: str, user_text: str, context: dict) -> tuple[str, list[str], list[str]]:
    if model is None:
        raise RuntimeError("model unavailable")

    lang_name = language_name(language_code)
    quality_rules = (
        "Phrase next_actions as natural checklist items in the same language as the response: one clear action per line. "
        "P0 = single most important outcome today; P1 = concrete today tasks; P2 = wrap-up or end-of-day. "
        "Do not repeat the same idea across items; avoid generic filler."
    )
    if language_code == "hu":
        quality_rules += " Use natural Hungarian (e.g. imperative or first-person plural); no English section titles."
    prompt = (
        f"Respond in {lang_name}.\n"
        "Return ONLY valid JSON object, no markdown, no extra text.\n"
        "Schema:\n"
        '{"answer_body":"string","assumptions":["string"],"next_actions":["string"]}\n'
        "Rules:\n"
        "- 5 to 8 next_actions\n"
        "- include priority markers P0/P1/P2 in next_actions\n"
        f"- {quality_rules}\n"
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


def get_structured_reply(
    answer: str,
    language_code: str,
    user_text: str,
    sources: list[str] | None = None,
    assumptions_override: list[str] | None = None,
    next_actions_override: list[str] | None = None,
) -> dict[str, Any]:
    planning = is_daily_planning_request(user_text)
    source_lines = [s for s in (sources or []) if s.strip()]
    # Planning defaults when no overrides: minimal only; no hardcoded plan content.
    if planning and language_code == "hu":
        assumptions = ["Feltételezés: napi terv nem áll rendelkezésre; a modell válaszából kell használni."]
        next_actions = ["P1 [ ] Próbáld újra a napi tervezést, vagy folytasd a chatet."]
    elif planning:
        assumptions = ["Assumption: no plan content available; use model response only."]
        next_actions = ["P1 [ ] Retry daily planning or continue the chat."]
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

    return {
        "answer": answer_clean,
        "language_code": language_code,
        "assumptions": assumptions,
        "next_actions": next_actions,
        "sources": source_lines,
        "planning": planning,
        "connectivity_state": "OFFLINE"
    }


def render_chat_default_output(
    answer: str,
    language_code: str,
    user_text: str,
    sources: list[str] | None = None,
    assumptions_override: list[str] | None = None,
    next_actions_override: list[str] | None = None,
) -> str:
    struct = get_structured_reply(
        answer=answer,
        language_code=language_code,
        user_text=user_text,
        sources=sources,
        assumptions_override=assumptions_override,
        next_actions_override=next_actions_override
    )

    if not struct["planning"]:
        return struct["answer"]

    assumptions_text = "\n".join(f"- {x}" for x in struct["assumptions"])
    actions_text = "\n".join(struct["next_actions"])
    if language_code == "hu":
        parts = [struct["answer"]]
        if assumptions_text:
            parts.append(f"Feltételezések:\n{assumptions_text}")
        if actions_text:
            parts.append(f"Következő lépések:\n{actions_text}")
        return "\n\n".join([p for p in parts if p.strip()])

    parts = [struct["answer"]]
    if assumptions_text:
        parts.append(f"Assumptions:\n{assumptions_text}")
    if actions_text:
        parts.append(f"Next actions:\n{actions_text}")
    return "\n\n".join([p for p in parts if p.strip()])


def layout(title: str, inner: str) -> str:
    ver = _app_version()
    nav = (
        "<div class='top'><div class='brand'>{hatori} v" + _h(ver) + "</div><div class='nav'>"
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
    return HTMLResponse(layout("{hatori}", "<div class='card'><p>Local dashboard.</p></div>"))


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
    db_error = ""
    try:
        rows = load_chat_rows(chat_id=chat_id, limit=300)
        recent_chats = load_recent_chats(limit=40)
    except Exception as exc:
        # Degrade gracefully when DB container is unavailable; keep chat UI reachable.
        rows = []
        recent_chats = []
        db_error = str(exc)

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
    if db_error:
        body.append(
            "<div class='msg-user'>"
            "<strong>Database unavailable.</strong> "
            "History is temporarily unavailable, but the UI is still running."
            f"<div class='ts'>{_h(db_error)}</div>"
            "</div>"
        )
    body.append(
        "<div class='chat-actions'>"
        "<a href='/chat?new=1'><button type='button'>New chat</button></a>"
        f"<form method='post' action='/chat/archive'>"
        f"<input type='hidden' name='chat_id' value='{_h(chat_id)}'>"
        "<button type='submit'>Archive chat</button>"
        "</form>"
        "</div>"
    )

    body.append("<div id='chat_messages'>")
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
    body.append("</div>")
    body.append(
        "<h3>Send message</h3>"
        "<form id='chat_form' method='post' action='/chat/send'>"
        f"<input type='hidden' name='chat_id' value='{_h(chat_id)}'>"
        "<textarea id='message_box' name='message' rows='3' placeholder='Type your message'></textarea>"
        "<button id='chat_send_btn' type='submit'>Send</button>"
        "</form>"
        "<script>"
        "(function(){"
        "var form=document.getElementById('chat_form');"
        "var box=document.getElementById('message_box');"
        "var btn=document.getElementById('chat_send_btn');"
        "if(!form||!box||!btn){return;}"
        "var sending=false;"
        "function setSending(v){sending=v;btn.disabled=v;btn.textContent=v?'Sending...':'Send';}"
        "function patchMessagesFromHtml(html){"
        "var parser=new DOMParser();"
        "var doc=parser.parseFromString(html,'text/html');"
        "var next=doc.getElementById('chat_messages');"
        "var current=document.getElementById('chat_messages');"
        "if(next&&current){current.outerHTML=next.outerHTML;}"
        "}"
        "async function sendAsync(){"
        "if(sending){return;}"
        "if(!box.value.trim()){return;}"
        "setSending(true);"
        "try{"
        "var resp=await fetch(form.action,{method:'POST',body:new FormData(form),credentials:'same-origin'});"
        "var html=await resp.text();"
        "patchMessagesFromHtml(html);"
        "box.value='';"
        "}catch(_e){"
        "form.submit();"
        "}finally{"
        "setSending(false);"
        "}"
        "}"
        "box.addEventListener('keydown',function(ev){"
        "if(ev.key==='Enter' && !ev.shiftKey){ev.preventDefault(); sendAsync();}"
        "});"
        "form.addEventListener('submit',function(ev){ev.preventDefault(); sendAsync();});"
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

    if is_greeting_only(text_raw, language_code):
        greeting_text = greeting_clarifying_answer(language_code)
        answer = render_chat_default_output(greeting_text, language_code, text_raw, sources=source_lines)
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

    conn_state = connectivity_state()
    web_hits: list[dict[str, str]] = []
    system_hints: list[str] = []
    weather_data: dict = {}
    
    needs_online_search = should_route_online_search(text_raw, conn_state)
    
    if needs_online_search and conn_state == "OFFLINE":
        system_hints.append("User requested an online search but the system is OFFLINE. Explain this limitation gracefully.")
    if needs_online_search and conn_state != "OFFLINE":
        if is_weather_request(text_raw):
            try:
                weather_data = fetch_live_weather(_extract_weather_location(text_raw))
            except Exception:
                weather_data = {}
            if weather_data:
                system_hints.append("Weather data found. Present it naturally as part of the conversation.")
        
        try:
            web_hits = online_search_snippets(text_raw, limit=5)
        except Exception:
            web_hits = []
        
        if web_hits:
            system_hints.append("Online search snippets provided. Use them to answer the user request directly.")

    is_planning = is_daily_planning_request(text_raw)
    if is_planning:
        model_task = "plan_write"
    else:
        model_task = "reply_write"
    model, adapter_error = select_chat_model_adapter(task=model_task)
    if is_planning:
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
                # No hardcoded plan content: surface error and retry guidance only.
                if language_code == "hu":
                    plan_answer = "A helyi modell nem elérhető. Kérlek indítsd el az Ollama szolgáltatást, majd próbáld újra."
                    assumptions = ["Feltételezés: helyi modell jelenleg nem elérhető."]
                    actions = ["P0 [ ] Indítsd el az Ollama szolgáltatást.", "P1 [ ] Küldd újra a napi tervezési kérést."]
                else:
                    plan_answer = "Local model is unavailable. Start Ollama and try again."
                    assumptions = ["Assumption: local model is currently unavailable."]
                    actions = ["P0 [ ] Start Ollama service.", "P1 [ ] Resend the daily planning request."]

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
    drafter_pack = build_drafter_context_pack(text_raw, language_code, history_turns, pks_rows, evidence_rows)
    task_prompt = build_task_prompt(
        user_text=text_raw,
        connectivity=conn_state,
        system_hints=system_hints,
        retrieved_context={
            "source": "ui.chat",
            "recent_history": [{"role": (x.get("role") or ""), "content": (x.get("content") or "")[:220]} for x in history_turns[-6:]],
            "pks_approved": summarize_pks_for_model(pks_rows, limit=4),
            "local_evidence_top": summarize_evidence_for_model(evidence_rows, limit=4),
            "drafter_pack": drafter_pack,
            "recent_feedback_summary": summarize_recent_learning_for_model(limit=15),
            "online_search_top": web_hits,
            "live_weather": weather_data,
        },
    )
    if needs_online_search:
        task_prompt += (
            "\nOnline retrieval requirements:\n"
            "- Use provided online snippets as primary fresh context.\n"
            "- If snippets conflict, state uncertainty briefly.\n"
            "- Add source URLs at the end under 'Sources:' as a flat list.\n"
            f"- Online snippets:\n{build_online_context_block(web_hits)}\n"
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
        raw_answer = localized_model_error(language_code, "No response generated.")

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
            "connectivity_state": conn_state,
            "online_search_used": bool(web_hits),
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
        f"'{_esc_sql(media_type)}', '{sha}', {_jsonb_sql_literal(metadata)});"
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
                f"'{emb_sql}'::vector, {_jsonb_sql_literal(cmeta)});"
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
    uri = _esc_sql(str(path))
    title = _esc_sql(filename)
    psql(
        "INSERT INTO artefacts (id, kind, uri, title, media_type, metadata) "
        f"VALUES ('{artefact_id}', 'export', '{uri}', '{title}', 'application/json', {_jsonb_sql_literal({'source': 'ui', 'export': 'snapshot'})});"
    )
    audit("export_snapshot", "artefact", artefact_id, {"uri": str(path)})
    return RedirectResponse(url="/pks/all", status_code=303)
