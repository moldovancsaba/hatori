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
from hatori.prompts import render_default_output
from hatori.cli import search_runtime

CID = os.environ.get("CID", "hatori-pg")
UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
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
        "SELECT t.chat_id, t.occurred_at AS last_at, t.role AS last_role, t.content AS last_content "
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
        "SELECT id, module, status, title, body "
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
        "heti terv",
        "tervez",
        "ütemez",
    ]
    return any(m in lowered for m in markers)


def render_chat_default_output(answer: str, language_code: str, user_text: str) -> str:
    planning = is_daily_planning_request(user_text)
    if planning and language_code == "hu":
        assumptions = [
            "Feltételezés: a felhasználó aktuális nyelve magyar.",
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
            f"Language mode selected from current user message: {language_name(language_code)}.",
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
                "Feltételezés: a felhasználó aktuális nyelve magyar.",
                "Feltételezés: OFFLINE módban dolgozunk, webes forrás nélkül.",
            ]
            next_actions = ["- [ ] Folytasd a beszélgetést egy konkrét következő kérdéssel a pontosításhoz."]
        else:
            assumptions = [
                f"Language mode selected from current user message: {language_name(language_code)}.",
                "Offline local runtime only; no web retrieval used.",
            ]
            next_actions = ["- [ ] Continue the chat with one concrete follow-up question for refinement."]
    if language_code == "hu":
        evidence = "- Nincs helyi bizonyíték."
        assumptions_text = "\n".join(f"- {x}" for x in assumptions)
        actions_text = "\n".join(next_actions)
        return (
            "1) Kapcsolati állapot: OFFLINE\n"
            "2) Válasz / Javaslat\n"
            f"{answer}\n\n"
            "3) Bizonyítékok és Források\n"
            f"{evidence}\n\n"
            "4) Feltételezések és Bizonytalanságok\n"
            f"{assumptions_text}\n\n"
            "5) Következő lépések\n"
            f"{actions_text}\n\n"
            "6) Memória patch\n"
            "Nincs memória módosítás.\n\n"
            "7) Tanulási napló (J)\n"
            "Nincs rögzített tanulási esemény."
        )

    payload = {
        "connectivity_state": "OFFLINE",
        "answer": answer,
        "evidence": [],
        "assumptions": assumptions,
        "next_actions": next_actions,
        "memory_patch": "No memory changes.",
        "learning_log": "No learning event recorded.",
    }
    return render_default_output(payload)


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
        preview = (c.get("last_content") or "").strip().replace("\n", " ")
        preview = preview[:60] + ("..." if len(preview) > 60 else "")
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

    history_turns = load_chat_history_for_prompt(chat_id=chat_id, limit=10)
    pks_rows = load_pks_context(limit=6)
    evidence_rows = load_local_evidence_context(query=text_raw, limit=5)
    prev_user_summary = summarize_prev_user_turn(history_turns)

    user_id = insert_interaction("user", text_raw, {"source": "ui", "chat_id": chat_id})

    language_code = detect_message_language(text_raw)
    model, adapter_error = select_chat_model_adapter()
    system_prompt = build_system_prompt()
    task_prompt = build_task_prompt(
        user_text=text_raw,
        connectivity="OFFLINE",
        retrieved_context={
            "chat_id": chat_id,
            "source": "ui.chat",
            "history_turns": history_turns,
            "pks_approved": pks_rows,
            "local_evidence_top": evidence_rows,
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
            clean_answer = "Nem tudok biztonságos, tiszta választ adni ebben a formában. Kérlek próbáld újra rövidebb kéréssel."

    if prev_user_summary:
        if language_code == "hu":
            clean_answer = f"Előzmény szerint: {prev_user_summary}\n{clean_answer}"
        else:
            clean_answer = f"Context from previous turn: {prev_user_summary}\n{clean_answer}"

    clean_answer = sanitize_assistant_output(clean_answer)
    if not clean_answer:
        clean_answer = localized_model_error(language_code, "empty sanitized output")
    answer = render_chat_default_output(clean_answer, language_code, text_raw)

    insert_interaction(
        "assistant",
        answer,
        {
            "source": "ui",
            "chat_id": chat_id,
            "model_adapter": model.name if model is not None else "unavailable",
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
