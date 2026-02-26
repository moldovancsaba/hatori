import os, sys, json, uuid, subprocess, re

CID = os.environ.get("CID", "hatori-pg")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

def _esc_sql(s: str) -> str:
    return s.replace("\\\\", "\\\\\\\\").replace("\x27", "\x27\x27")

def psql(sql: str) -> str:
    cmd = ["docker","exec","-i",CID,"psql","-U","hatori","-d","hatori","-t","-A","-c",sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(r.stderr.strip() or "psql failed")
    return r.stdout.strip()

def ping() -> None:
    out = psql("SELECT 1;")
    print("OK" if out == "1" else out)

def last_interaction_id() -> str | None:
    out = psql("SELECT id FROM interaction_events ORDER BY occurred_at DESC LIMIT 1;")
    return out if out else None

def log(role: str, content: str, meta: dict) -> None:
    eid = str(uuid.uuid4())
    meta_json = json.dumps(meta, ensure_ascii=False)
    sql = ("INSERT INTO interaction_events (id, role, content, metadata) "
           f"VALUES (\x27{eid}\x27, \x27{_esc_sql(role)}\x27, \x27{_esc_sql(content)}\x27, \x27{_esc_sql(meta_json)}\x27::jsonb);")
    psql(sql)
    print(eid)

def feedback(kind: str, confidence: str, details: dict, interaction_id: str | None) -> None:
    lid = str(uuid.uuid4())
    det_json = json.dumps(details, ensure_ascii=False)
    if interaction_id:
        if not UUID_RE.match(interaction_id):
            raise SystemExit("interaction_id must be a UUID")
        sql = ("INSERT INTO learning_events (id, kind, confidence, details, related_interaction_id) "
               f"VALUES (\x27{lid}\x27, \x27{_esc_sql(kind)}\x27, \x27{_esc_sql(confidence)}\x27, \x27{_esc_sql(det_json)}\x27::jsonb, \x27{interaction_id}\x27);")
    else:
        sql = ("INSERT INTO learning_events (id, kind, confidence, details) "
               f"VALUES (\x27{lid}\x27, \x27{_esc_sql(kind)}\x27, \x27{_esc_sql(confidence)}\x27, \x27{_esc_sql(det_json)}\x27::jsonb);")
    psql(sql)
    print(lid)

def pks_add(module: str, title: str, body: str, status: str) -> None:
    rid = str(uuid.uuid4())
    if module not in list("ABCDEFGHIJ"):
        raise SystemExit("module must be A..J")
    if status not in ["Pending","Approved","Deprecated","Contested"]:
        raise SystemExit("status must be Pending|Approved|Deprecated|Contested")
    sql = ("INSERT INTO pks_records (id,module,title,body,status,provenance,confidence,scope) "
           f"VALUES (\x27{rid}\x27,\x27{module}\x27,\x27{_esc_sql(title)}\x27,\x27{_esc_sql(body)}\x27,\x27{status}\x27,\x27User\x27,\x27High\x27,\x27Personal\x27);")
    psql(sql)
    print(rid)

def pks_list(module: str | None, status: str | None, limit: int) -> None:
    where = []
    if module: where.append(f"module=\x27{_esc_sql(module)}\x27")
    if status: where.append(f"status=\x27{_esc_sql(status)}\x27")
    w = (" WHERE " + " AND ".join(where)) if where else ""
    sql = f"SELECT id, module, status, title, updated_at FROM pks_records{w} ORDER BY updated_at DESC LIMIT {int(limit)};"
    print(psql(sql))

def pks_show(rid: str) -> None:
    if not UUID_RE.match(rid): raise SystemExit("id must be a UUID")
    sql = f"SELECT id, module, status, title, body, provenance, confidence, scope, created_at, updated_at FROM pks_records WHERE id=\x27{rid}\x27;"
    print(psql(sql))

def audit(action: str, target_type: str, target_id: str, details: dict) -> None:
    det_json = json.dumps(details, ensure_ascii=False)
    sql = ("INSERT INTO audit_events (id, actor, action, target_type, target_id, details) "
           f"VALUES (gen_random_uuid(), \x27cli\x27, \x27{_esc_sql(action)}\x27, \x27{_esc_sql(target_type)}\x27, \x27{_esc_sql(target_id)}\x27, \x27{_esc_sql(det_json)}\x27::jsonb);")
    psql(sql)

def pks_set_status(rid: str, status: str, reason: dict | None = None) -> None:
    if not UUID_RE.match(rid): raise SystemExit("id must be a UUID")
    if status not in ["Pending","Approved","Deprecated","Contested"]:
        raise SystemExit("status must be Pending|Approved|Deprecated|Contested")
    psql(f"UPDATE pks_records SET status=\x27{status}\x27, updated_at=now() WHERE id=\x27{rid}\x27;")
    action_map = {
        "Approved": "approve",
        "Deprecated": "deprecate",
        "Contested": "contest",
        "Pending": "set_pending",
    }
    action = action_map[status]
    details = {"status": status}
    if reason is not None:
        details["reason"] = reason
    audit(action, "pks_record", rid, details)
    print("OK")

def main(argv: list[str]) -> None:
    if len(argv) < 2: raise SystemExit("Usage: hatori <ping|log|feedback|pks> ...")
    cmd = argv[1]
    if cmd == "ping": ping(); return
    if cmd == "log":
        if len(argv) < 4: raise SystemExit("Usage: hatori log <role> <content>")
        log(argv[2], " ".join(argv[3:]), {"source":"cli"}); return
    if cmd == "feedback":
        if len(argv) >= 3 and argv[2] == "--last":
            if len(argv) < 6: raise SystemExit("Usage: hatori feedback --last <kind> <confidence> <details_json>")
            iid = last_interaction_id()
            if not iid: raise SystemExit("No interactions found.")
            feedback(argv[3], argv[4], json.loads(argv[5]), iid); return
        if len(argv) < 5: raise SystemExit("Usage: hatori feedback <kind> <confidence> <details_json> [interaction_id]")
        iid = argv[5] if len(argv) >= 6 else None
        feedback(argv[2], argv[3], json.loads(argv[4]), iid); return
    if cmd == "pks":
        if len(argv) < 3: raise SystemExit("Usage: hatori pks <add|list|show|approve|deprecate|contest> ...")
        sub = argv[2]
        if sub == "add":
            if len(argv) < 6: raise SystemExit("Usage: hatori pks add <module> <title> <body> [--status Pending|Approved]")
            status = "Pending"
            if len(argv) >= 8 and argv[6] == "--status": status = argv[7]
            pks_add(argv[3], argv[4], argv[5], status); return
        if sub == "list":
            module=None; status=None; limit=20; i=3
            while i < len(argv):
                if argv[i] == "--module": module=argv[i+1]; i+=2; continue
                if argv[i] == "--status": status=argv[i+1]; i+=2; continue
                if argv[i] == "--limit": limit=int(argv[i+1]); i+=2; continue
                raise SystemExit("Unknown option: " + argv[i])
            pks_list(module, status, limit); return
        if sub == "show":
            if len(argv) < 4: raise SystemExit("Usage: hatori pks show <uuid>")
            pks_show(argv[3]); return
        if sub == "approve":
            if len(argv) < 4: raise SystemExit("Usage: hatori pks approve <uuid>")
            pks_set_status(argv[3], "Approved"); return
        if sub == "deprecate":
            if len(argv) < 4: raise SystemExit("Usage: hatori pks deprecate <uuid>")
            pks_set_status(argv[3], "Deprecated"); return
        if sub == "contest":
            if len(argv) < 5: raise SystemExit("Usage: hatori pks contest <uuid> <reason_json>")
            reason = json.loads(argv[4])
            pks_set_status(argv[3], "Contested", reason); return
        raise SystemExit("Unknown pks subcommand: " + sub)
    raise SystemExit("Unknown command: " + cmd)

if __name__ == "__main__":
    main(sys.argv)
