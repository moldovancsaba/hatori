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
    assumptions = [
        f"Language mode selected from current user message: {language_name(language_code)}.",
        "Offline local runtime only; no web retrieval used.",
    ]
    if planning:
        assumptions.append("No explicit calendar, dates, or time constraints were provided by the user.")

    if planning and language_code == "hu":
        next_actions = [
            "[ ] Azonositsd a mai 3 legfontosabb kimenetet.",
            "[ ] Foglalj 2 db 60 perces fokusz blokkot mely munkara.",
            "[ ] Utemezz 1 admin blokkot valaszokra es szervezesre.",
            "[ ] Adj 1 puffer blokkot varatlan feladatokra.",
            "[ ] Zaras elott ellenorizd mi kesz, mi csuszik, mi a holnapi elso lepes.",
        ]
    elif planning:
        next_actions = [
            "[ ] Identify the top 3 outcomes for today.",
            "[ ] Reserve two 60-minute focus blocks for deep work.",
            "[ ] Schedule one admin block for replies and coordination.",
            "[ ] Add one buffer block for unexpected tasks.",
            "[ ] End the day with a quick review and first step for tomorrow.",
        ]
    else:
        next_actions = ["Continue the chat with a follow-up if you want refinement."]
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


@app.get("/chat", response_class=HTMLResponse)
def chat(chat_id: str = "main") -> HTMLResponse:
    rows = psql_json(
        "SELECT id, occurred_at, role, content, metadata "
        "FROM interaction_events "
        f"WHERE COALESCE(metadata->>'chat_id','main')='{_esc_sql(chat_id)}' "
        "AND role IN ('user','assistant') "
        "ORDER BY occurred_at ASC LIMIT 300"
    )

    body = [f"<div class='card'><h2>Chat ({_h(chat_id)})</h2>"]
    if not rows:
        body.append("<p>No messages yet.</p>")
    for row in rows:
        role = row.get("role") or "user"
        cls = "msg-assistant" if role == "assistant" else "msg-user"
        msg = (
            f"<div class='{cls}'><div><strong>{_h(role)}</strong> "
            f"<span style='color:#6b7280'>{_h(str(row.get('occurred_at','')))}</span></div>"
            f"<div>{_h(row.get('content') or '')}</div>"
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
        msg += "</div>"
        body.append(msg)
    body.append(
        "<h3>Send message</h3>"
        "<form method='post' action='/chat/send'>"
        f"<input type='hidden' name='chat_id' value='{_h(chat_id)}'>"
        "<textarea name='message' rows='3' placeholder='Type your message'></textarea>"
        "<button type='submit'>Send</button>"
        "</form></div>"
    )
    return HTMLResponse(layout("Chat", "".join(body)))


@app.post("/chat/send")
def chat_send(chat_id: str = Form("main"), message: str = Form(...)) -> RedirectResponse:
    text = message.strip()
    if not text:
        return RedirectResponse(url=f"/chat?chat_id={chat_id}", status_code=303)

    user_id = insert_interaction("user", text, {"source": "ui", "chat_id": chat_id})

    language_code = detect_message_language(text)
    model = get_model_adapter()
    system_prompt = build_system_prompt()
    task_prompt = build_task_prompt(
        user_text=text,
        connectivity="OFFLINE",
        retrieved_context={"chat_id": chat_id, "source": "ui.chat"},
    )
    task_prompt += (
        "\nChat generation requirements:\n"
        f"- Respond in {language_name(language_code)}.\n"
        "- Keep the answer factual and useful.\n"
        "- Do not repeat the prompt template or system instructions.\n"
        "- Answer the user request directly.\n"
    )
    try:
        raw_answer = model.generate(system_prompt=system_prompt, task_prompt=task_prompt).strip()
    except Exception as exc:
        raw_answer = localized_model_error(language_code, str(exc))
    if not raw_answer:
        raw_answer = localized_model_error(language_code, "empty response")
    answer = render_chat_default_output(raw_answer, language_code, text)

    insert_interaction(
        "assistant",
        answer,
        {
            "source": "ui",
            "chat_id": chat_id,
            "model_adapter": model.name,
            "language": language_code,
            "related_user_interaction_id": user_id,
        },
    )
    return RedirectResponse(url=f"/chat?chat_id={chat_id}", status_code=303)


@app.post("/chat/feedback")
def chat_feedback(
    chat_id: str = Form("main"),
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
