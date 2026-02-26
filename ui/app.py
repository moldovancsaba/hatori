import os, subprocess, re, json
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

CID = os.environ.get("CID", "hatori-pg")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ROOT_DIR = Path(__file__).resolve().parent.parent
EXPORT_DIR = ROOT_DIR / "artefacts" / "exports"

def _esc_sql(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "''")

def psql(sql: str) -> str:
    cmd = ["docker","exec","-i",CID,"psql","-U","hatori","-d","hatori","-t","-A","-F","|","-c",sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return "ERROR: " + (r.stderr.strip() or "psql failed")
    return r.stdout.strip()

app = FastAPI()

CSS = "body{font-family:system-ui;max-width:1100px;margin:24px auto;padding:0 16px} a{color:#0a58ca;text-decoration:none} a:hover{text-decoration:underline} .top{display:flex;justify-content:space-between;align-items:center} .brand{font-size:42px;font-weight:800} .nav a{margin-right:14px;font-weight:600} .card{border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px;margin:12px 0} pre{white-space:pre-wrap;background:#f8fafc;border:1px solid #e5e7eb;border-radius:10px;padding:12px}"

def layout(title: str, inner: str) -> str:
    nav = "<div class='top'><div class='brand'>Hatori</div><div class='nav'><a href='/interactions'>Interactions</a><a href='/learning'>Learning</a><a href='/pks/pending'>PKS Pending</a><a href='/pks/all'>PKS All</a><a href='/export.json'>Export JSON</a><form style='display:inline; margin-left:8px' method='post' action='/export/disk'><button type='submit'>Export to Disk</button></form></div></div>"
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title><style>{CSS}</style></head><body>{nav}{inner}</body></html>"

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(layout("Hatori","<div class='card'><p>Local dashboard.</p></div>"))

@app.get("/interactions", response_class=HTMLResponse)
def interactions():
    rows = psql("SELECT occurred_at, role, content, id FROM interaction_events ORDER BY occurred_at DESC LIMIT 100;")
    return HTMLResponse(layout("Interactions", f"<div class='card'><h2>Interactions</h2><pre>{rows}</pre></div>"))

@app.get("/learning", response_class=HTMLResponse)
def learning():
    rows = psql("SELECT occurred_at, kind, confidence, details, related_interaction_id FROM learning_events ORDER BY occurred_at DESC LIMIT 100;")
    return HTMLResponse(layout("Learning", f"<div class='card'><h2>Learning</h2><pre>{rows}</pre></div>"))

@app.get("/pks/pending", response_class=HTMLResponse)
def pks_pending():
    rows = psql("SELECT id, module, status, title, updated_at FROM pks_records WHERE status='Pending' ORDER BY updated_at DESC LIMIT 200;")
    inner = "<div class='card'><h2>PKS Pending</h2>"
    inner += "<table style='width:100%; border-collapse:collapse'><tr><th style='text-align:left; padding:6px'>Module</th><th style='text-align:left; padding:6px'>Title</th><th style='text-align:left; padding:6px'>Updated</th><th style='text-align:left; padding:6px'>Actions</th></tr>"
    for line in rows.splitlines():
        parts = line.split("|")
        if len(parts) < 5: continue
        rid, module, status, title, updated_at = parts[0], parts[1], parts[2], parts[3], parts[4]
        inner += "<tr>"
        inner += f"<td style='padding:6px'>{module}</td>"
        inner += f"<td style='padding:6px'><div><a href='/pks/{rid}'>{title}</a></div><div style='color:#6b7280; font-size:12px'>{rid}</div></td>"
        inner += f"<td style='padding:6px; color:#6b7280'>{updated_at}</td>"
        inner += "<td style='padding:6px'>"
        inner += f"<form style='display:inline-block; margin-right:8px' method='post' action='/pks/approve'><input type='hidden' name='id' value='{rid}'><input style='margin-right:6px' name='reason' placeholder='reason (optional)'><button>Approve</button></form> "
        inner += f"<form style='display:inline-block' method='post' action='/pks/deprecate'><input type='hidden' name='id' value='{rid}'><input style='margin-right:6px' name='reason' placeholder='reason (optional)'><button>Deprecate</button></form>"
        inner += "</td></tr>"
    inner += "</table></div>"
    return HTMLResponse(layout("PKS Pending", inner))


@app.get("/pks/all", response_class=HTMLResponse)
def pks_all():
    rows = psql("SELECT id, module, status, title, updated_at FROM pks_records ORDER BY updated_at DESC LIMIT 300;")
    lines = []
    for line in rows.splitlines():
        parts = line.split("|")
        if len(parts) < 5:
            continue
        rid, module, status, title, updated_at = parts[0], parts[1], parts[2], parts[3], parts[4]
        lines.append(f"<tr><td style='padding:6px'><a href='/pks/{rid}'>{rid}</a></td><td style='padding:6px'>{module}</td><td style='padding:6px'>{status}</td><td style='padding:6px'>{title}</td><td style='padding:6px'>{updated_at}</td></tr>")
    inner = "<div class='card'><h2>PKS</h2><table style='width:100%; border-collapse:collapse'><tr><th style='text-align:left; padding:6px'>ID</th><th style='text-align:left; padding:6px'>Module</th><th style='text-align:left; padding:6px'>Status</th><th style='text-align:left; padding:6px'>Title</th><th style='text-align:left; padding:6px'>Updated</th></tr>"
    inner += "".join(lines) + "</table></div>"
    return HTMLResponse(layout("PKS", inner))

@app.post("/pks/approve")
def approve(id: str = Form(...), reason: str = Form(default="")):
    if not UUID_RE.match(id):
        return HTMLResponse(layout("Error","<div class='card'><h2>Invalid UUID</h2></div>"), status_code=400)
    psql(f"UPDATE pks_records SET status='Approved', updated_at=now() WHERE id='{id}';")
    details = {"status":"Approved"}
    if reason.strip():
        details["reason"] = reason.strip()
    audit("approve","pks_record",id,details)
    return RedirectResponse(url="/pks/pending", status_code=303)

@app.post("/pks/deprecate")
def deprecate(id: str = Form(...), reason: str = Form(default="")):
    if not UUID_RE.match(id):
        return HTMLResponse(layout("Error","<div class='card'><h2>Invalid UUID</h2></div>"), status_code=400)
    psql(f"UPDATE pks_records SET status='Deprecated', updated_at=now() WHERE id='{id}';")
    details = {"status":"Deprecated"}
    if reason.strip():
        details["reason"] = reason.strip()
    audit("deprecate","pks_record",id,details)
    return RedirectResponse(url="/pks/pending", status_code=303)

@app.get("/pks/{rid}", response_class=HTMLResponse)
def pks_detail(rid: str):
    if not UUID_RE.match(rid):
        return HTMLResponse(layout("Error","<div class='card'><h2>Invalid UUID</h2></div>"), status_code=400)
    rec = psql(f"SELECT id, module, status, title, body, provenance, confidence, scope, created_at, updated_at FROM pks_records WHERE id='{rid}' LIMIT 1;")
    if not rec.strip():
        return HTMLResponse(layout("Not Found","<div class='card'><h2>Record not found</h2></div>"), status_code=404)
    parts = rec.split("|")
    if len(parts) < 10:
        return HTMLResponse(layout("Error","<div class='card'><h2>Unexpected record payload</h2></div>"), status_code=500)
    body = (
        "<div class='card'>"
        f"<h2>{parts[3]}</h2>"
        f"<p><strong>ID:</strong> {parts[0]}</p>"
        f"<p><strong>Module:</strong> {parts[1]} | <strong>Status:</strong> {parts[2]}</p>"
        f"<p><strong>Provenance:</strong> {parts[5]} | <strong>Confidence:</strong> {parts[6]} | <strong>Scope:</strong> {parts[7]}</p>"
        f"<p><strong>Created:</strong> {parts[8]} | <strong>Updated:</strong> {parts[9]}</p>"
        f"<h3>Body</h3><pre>{parts[4]}</pre>"
        "<div style='margin-top:12px'>"
        f"<form style='display:inline-block; margin-right:8px' method='post' action='/pks/approve'><input type='hidden' name='id' value='{rid}'><input style='margin-right:6px' name='reason' placeholder='reason (optional)'><button>Approve</button></form>"
        f"<form style='display:inline-block' method='post' action='/pks/deprecate'><input type='hidden' name='id' value='{rid}'><input style='margin-right:6px' name='reason' placeholder='reason (optional)'><button>Deprecate</button></form>"
        "</div>"
        "</div>"
    )
    return HTMLResponse(layout("PKS Detail", body))


def audit(action: str, target_type: str, target_id: str, details: dict):
    det = _esc_sql(json.dumps(details, ensure_ascii=False))
    sql = ("INSERT INTO audit_events (id, actor, action, target_type, target_id, details) "
           f"VALUES (gen_random_uuid(), \x27ui\x27, \x27{_esc_sql(action)}\x27, \x27{_esc_sql(target_type)}\x27, \x27{_esc_sql(target_id)}\x27, \x27{det}\x27::jsonb);")
    psql(sql)


from fastapi.responses import JSONResponse

@app.get("/export.json")
def export_json():
    def q(sql: str):
        cmd = ["docker","exec","-i",CID,"psql","-U","hatori","-d","hatori","-t","-A","-c",f"SELECT COALESCE(json_agg(t), '[]'::json) FROM ({sql}) t;"]
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
def export_disk():
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
