import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
import uuid

from hatori.embeddings import EmbeddingsAdapter
from hatori.embeddings import get_embeddings_adapter
from hatori.model import get_model_adapter
from hatori.model import get_task_model_adapter
from hatori.prompts import build_system_prompt
from hatori.prompts import build_task_prompt
from hatori.prompts import render_default_output

CID = os.environ.get("CID", "hatori-pg")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_EMBED_ADAPTER: EmbeddingsAdapter | None = None


def _esc_sql(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\x27", "\x27\x27")


def psql(sql: str) -> str:
    cmd = ["docker", "exec", "-i", CID, "psql", "-U", "hatori", "-d", "hatori", "-t", "-A", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(r.stderr.strip() or "psql failed")
    return r.stdout.strip()


def psql_json(sql: str) -> list[dict]:
    wrapped = f"SELECT COALESCE(json_agg(t), '[]'::json) FROM ({sql}) t;"
    out = psql(wrapped)
    if not out:
        return []
    return json.loads(out)


def embedding_adapter() -> EmbeddingsAdapter:
    global _EMBED_ADAPTER
    if _EMBED_ADAPTER is None:
        _EMBED_ADAPTER = get_embeddings_adapter()
    return _EMBED_ADAPTER


def vector_sql_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vector) + "]"


def connectivity_state() -> str:
    explicit = os.environ.get("HATORI_CONNECTIVITY_STATE", "").strip().upper()
    if explicit in {"OFFLINE", "ONLINE-UNVERIFIED", "ONLINE-VERIFIED"}:
        return explicit
    if os.environ.get("HATORI_ENABLE_ONLINE_VERIFIED", "").strip() == "1":
        return "ONLINE-VERIFIED"
    if os.environ.get("HATORI_ENABLE_ONLINE", "").strip() == "1":
        return "ONLINE-UNVERIFIED"
    return "OFFLINE"


def ping() -> None:
    out = psql("SELECT 1;")
    print("OK" if out == "1" else out)


def last_interaction_id() -> str | None:
    out = psql("SELECT id FROM interaction_events ORDER BY occurred_at DESC LIMIT 1;")
    return out if out else None


def insert_interaction(role: str, content: str, meta: dict, session_id: str | None = None) -> str:
    eid = str(uuid.uuid4())
    meta_json = json.dumps(meta, ensure_ascii=False)
    sid_sql = f"\x27{_esc_sql(session_id)}\x27" if session_id else "NULL"
    sql = (
        "INSERT INTO interaction_events (id, session_id, role, content, metadata) "
        f"VALUES (\x27{eid}\x27, {sid_sql}, \x27{_esc_sql(role)}\x27, \x27{_esc_sql(content)}\x27, \x27{_esc_sql(meta_json)}\x27::jsonb);"
    )
    psql(sql)
    return eid


def log(role: str, content: str, meta: dict) -> None:
    print(insert_interaction(role, content, meta))


def insert_learning(kind: str, confidence: str, details: dict, interaction_id: str | None = None) -> str:
    lid = str(uuid.uuid4())
    det_json = json.dumps(details, ensure_ascii=False)
    if interaction_id:
        if not UUID_RE.match(interaction_id):
            raise SystemExit("interaction_id must be a UUID")
        sql = (
            "INSERT INTO learning_events (id, kind, confidence, details, related_interaction_id) "
            f"VALUES (\x27{lid}\x27, \x27{_esc_sql(kind)}\x27, \x27{_esc_sql(confidence)}\x27, \x27{_esc_sql(det_json)}\x27::jsonb, \x27{interaction_id}\x27);"
        )
    else:
        sql = (
            "INSERT INTO learning_events (id, kind, confidence, details) "
            f"VALUES (\x27{lid}\x27, \x27{_esc_sql(kind)}\x27, \x27{_esc_sql(confidence)}\x27, \x27{_esc_sql(det_json)}\x27::jsonb);"
        )
    psql(sql)
    return lid


def feedback(kind: str, confidence: str, details: dict, interaction_id: str | None) -> None:
    print(insert_learning(kind, confidence, details, interaction_id))


def audit(action: str, target_type: str, target_id: str, details: dict) -> None:
    det_json = json.dumps(details, ensure_ascii=False)
    sql = (
        "INSERT INTO audit_events (id, actor, action, target_type, target_id, details) "
        f"VALUES (gen_random_uuid(), \x27cli\x27, \x27{_esc_sql(action)}\x27, \x27{_esc_sql(target_type)}\x27, \x27{_esc_sql(target_id)}\x27, \x27{_esc_sql(det_json)}\x27::jsonb);"
    )
    psql(sql)


def default_status_for_module(module: str) -> str:
    return "Pending" if module in {"B", "D", "F"} else "Approved"


def pks_add(module: str, title: str, body: str, status: str | None = None) -> None:
    rid = str(uuid.uuid4())
    if module not in list("ABCDEFGHIJ"):
        raise SystemExit("module must be A..J")
    final_status = status or default_status_for_module(module)
    if final_status not in ["Pending", "Approved", "Deprecated", "Contested"]:
        raise SystemExit("status must be Pending|Approved|Deprecated|Contested")

    sql = (
        "INSERT INTO pks_records (id,module,title,body,status,provenance,confidence,scope) "
        f"VALUES (\x27{rid}\x27,\x27{module}\x27,\x27{_esc_sql(title)}\x27,\x27{_esc_sql(body)}\x27,\x27{final_status}\x27,\x27User\x27,\x27High\x27,\x27Personal\x27);"
    )
    psql(sql)
    audit("create", "pks_record", rid, {"status": final_status, "module": module})
    print(rid)


def pks_list(module: str | None, status: str | None, limit: int) -> None:
    where = []
    if module:
        where.append(f"module=\x27{_esc_sql(module)}\x27")
    if status:
        where.append(f"status=\x27{_esc_sql(status)}\x27")
    w = (" WHERE " + " AND ".join(where)) if where else ""
    sql = f"SELECT id, module, status, title, updated_at FROM pks_records{w} ORDER BY updated_at DESC LIMIT {int(limit)};"
    print(psql(sql))


def pks_show(rid: str) -> None:
    if not UUID_RE.match(rid):
        raise SystemExit("id must be a UUID")
    sql = f"SELECT id, module, status, title, body, provenance, confidence, scope, created_at, updated_at FROM pks_records WHERE id=\x27{rid}\x27;"
    print(psql(sql))


def pks_set_status(rid: str, status: str, reason: dict | None = None) -> None:
    if not UUID_RE.match(rid):
        raise SystemExit("id must be a UUID")
    if status not in ["Pending", "Approved", "Deprecated", "Contested"]:
        raise SystemExit("status must be Pending|Approved|Deprecated|Contested")
    psql(f"UPDATE pks_records SET status=\x27{status}\x27, updated_at=now() WHERE id=\x27{rid}\x27;")
    action_map = {
        "Approved": "approve",
        "Deprecated": "deprecate",
        "Contested": "contest",
        "Pending": "set_pending",
    }
    details = {"status": status}
    if reason is not None:
        details["reason"] = reason
    audit(action_map[status], "pks_record", rid, details)
    print("OK")


def _extract_json_array(raw: str) -> list[dict[str, Any]]:
    """Parse JSON array of objects from model output; tolerate markdown fences."""
    text = (raw or "").strip()
    for start_marker in ("[", "```json\n[", "```\n["):
        start = text.find(start_marker)
        if start >= 0:
            text = text[start + len(start_marker) - 1:]
            break
    end = text.rfind("]")
    if end >= 0:
        text = text[: end + 1]
    try:
        out = json.loads(text)
        return out if isinstance(out, list) else []
    except json.JSONDecodeError:
        return []


def propose_pks_from_doc(path_or_artefact_id: str, max_chars: int = 6000) -> dict[str, Any]:
    """Extract PKS candidate records from a document (path or artefact_id); insert as Pending (provenance LocalDoc)."""
    text = ""
    if UUID_RE.match(path_or_artefact_id.strip()):
        rows = psql_json(
            f"SELECT content FROM embeddings WHERE artefact_id=\x27{_esc_sql(path_or_artefact_id.strip())}\x27 "
            "ORDER BY chunk_id LIMIT 50"
        )
        text = "\n".join((r.get("content") or "").strip() for r in rows if (r.get("content") or "").strip())
    else:
        path = Path(path_or_artefact_id).expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"Not a file: {path}")
        text = read_file_text(path)
    text = (text or "").strip()[:max_chars]
    if not text or len(text) < 80:
        return {"proposed": 0, "ids": [], "error": "Text too short or empty."}

    adapter, err, _ = get_task_model_adapter("extract_fields")
    if adapter is None:
        return {"proposed": 0, "ids": [], "error": f"Model unavailable: {err}"}

    prompt = (
        "From the following document text, extract 1 to 5 candidate PKS records (facts, preferences, decisions, or profile-like statements). "
        "Return ONLY a JSON array of objects, each with keys: module, title, body. "
        "module must be one of: A (Profile), B (Facts), C (Preferences), D (Projects), E (Tasks), F (Decisions). "
        "Only suggest items that are clearly stated or strongly implied. No markdown, no explanation.\n\n"
        f"Document text:\n{text}\n"
    )
    try:
        raw = adapter.generate(system_prompt="PKS extraction.", task_prompt=prompt).strip()
    except Exception as exc:
        return {"proposed": 0, "ids": [], "error": str(exc)}
    candidates = _extract_json_array(raw)
    allowed_modules = {"A", "B", "C", "D", "E", "F"}
    created: list[str] = []
    for item in candidates[:10]:
        if not isinstance(item, dict):
            continue
        mod = (item.get("module") or "").strip().upper()
        if len(mod) != 1 or mod not in allowed_modules:
            continue
        title = (item.get("title") or "").strip()[:500]
        body = (item.get("body") or "").strip()[:8000]
        if not title or not body:
            continue
        rid = str(uuid.uuid4())
        psql(
            "INSERT INTO pks_records (id, module, title, body, status, provenance, confidence, scope) "
            f"VALUES (\x27{rid}\x27, \x27{mod}\x27, \x27{_esc_sql(title)}\x27, \x27{_esc_sql(body)}\x27, "
            "\x27Pending\x27, \x27LocalDoc\x27, \x27Medium\x27, \x27Personal\x27);"
        )
        audit("create", "pks_record", rid, {"status": "Pending", "module": mod, "source": "propose_pks_from_doc"})
        created.append(rid)
    return {"proposed": len(created), "ids": created}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z0-9_]+", text.lower()) if len(t) >= 3]


def score_text(text: str, terms: list[str]) -> int:
    if not text or not terms:
        return 0
    low = text.lower()
    return sum(low.count(t) for t in terms)


def classify_request(question: str) -> str:
    q = question.lower()
    project_terms = ["project", "roadmap", "sprint", "milestone", "deliverable", "epic"]
    system_terms = ["setup", "configure", "docker", "database", "reset", "backup", "schema", "runtime", "service"]
    if any(t in q for t in project_terms):
        return "Project work"
    if any(t in q for t in system_terms):
        return "System upkeep"
    return "Daily task"


def retrieve_pks(question: str, allow_pending: bool, limit: int = 8) -> list[dict]:
    statuses = ["Approved"]
    if allow_pending:
        statuses.append("Pending")
    status_sql = ",".join(f"\x27{s}\x27" for s in statuses)
    rows = psql_json(
        "SELECT id, module, status, title, body, provenance, confidence, scope, updated_at "
        f"FROM pks_records WHERE status IN ({status_sql}) ORDER BY updated_at DESC LIMIT 400"
    )
    terms = tokenize(question)
    scored: list[dict] = []
    for row in rows:
        hay = f"{row.get('title','')}\n{row.get('body','')}"
        s = score_text(hay, terms)
        if s <= 0:
            continue
        scored.append(
            {
                "source_type": "pks",
                "citation": f"pks:{row['id']}",
                "score": s,
                "title": row.get("title") or "(untitled)",
                "excerpt": (row.get("body") or "").strip()[:220],
                "module": row.get("module"),
                "status": row.get("status"),
                "provenance": row.get("provenance"),
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def retrieve_embeddings(question: str, limit: int = 8) -> list[dict]:
    rows = psql_json(
        "SELECT e.id, e.chunk_id, e.content, e.artefact_id, e.metadata, a.uri, a.title "
        "FROM embeddings e "
        "LEFT JOIN artefacts a ON a.id = e.artefact_id "
        "ORDER BY e.created_at DESC LIMIT 800"
    )
    terms = tokenize(question)
    scored: list[dict] = []
    for row in rows:
        content = row.get("content") or ""
        s = score_text(content, terms)
        if s <= 0:
            continue
        scored.append(
            {
                "source_type": "embedding",
                "citation": f"emb:{row['chunk_id']}",
                "score": float(s),
                "title": row.get("title") or row.get("uri") or "(local artefact)",
                "excerpt": content.strip()[:220],
                "artefact_id": row.get("artefact_id"),
                "artefact_uri": row.get("uri"),
                "provenance": "LocalDoc",
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def retrieve_embeddings_semantic(question: str, limit: int = 8) -> list[dict]:
    adapter = embedding_adapter()
    query_vec = adapter.embed([question])[0]
    query_vec_sql = _esc_sql(vector_sql_literal(query_vec))
    query_terms = set(tokenize(question))
    sql_limit = max(limit * 4, 24)
    rows = psql_json(
        "SELECT e.id, e.chunk_id, e.content, e.artefact_id, e.metadata, a.uri, a.title, "
        f"(e.embedding <=> \x27{query_vec_sql}\x27::vector) AS distance "
        "FROM embeddings e "
        "LEFT JOIN artefacts a ON a.id = e.artefact_id "
        "WHERE e.embedding IS NOT NULL "
        f"ORDER BY e.embedding <=> \x27{query_vec_sql}\x27::vector ASC LIMIT {sql_limit}"
    )
    results: list[dict[str, Any]] = []
    for row in rows:
        content = row.get("content") or ""
        content_terms = set(tokenize(content))
        if query_terms and not (query_terms & content_terms):
            continue
        dist = float(row.get("distance", 1.0) or 1.0)
        score = 1.0 / (1.0 + max(0.0, dist))
        if score < 0.30:
            continue
        results.append(
            {
                "source_type": "embedding_semantic",
                "citation": f"emb:{row['chunk_id']}",
                "score": score,
                "title": row.get("title") or row.get("uri") or "(local artefact)",
                "excerpt": content.strip()[:220],
                "artefact_id": row.get("artefact_id"),
                "artefact_uri": row.get("uri"),
                "provenance": "LocalDoc",
            }
        )
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def merge_rank_results(candidates: list[dict], limit: int) -> list[dict]:
    by_citation: dict[str, dict] = {}
    for item in candidates:
        key = item.get("citation", "")
        if not key:
            continue
        current = by_citation.get(key)
        if current is None or float(item.get("score", 0.0)) > float(current.get("score", 0.0)):
            by_citation[key] = item
    merged = list(by_citation.values())
    merged.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    return merged[:limit]


def rerank_mode() -> str:
    """HATORI_RERANK_MODE: off (default) | lexical — Phase 3 #350, no extra model deps."""
    return (os.environ.get("HATORI_RERANK_MODE") or "off").strip().lower()


def rerank_merged_results(query: str, merged: list[dict], limit: int) -> list[dict]:
    """
    Second-stage rerank after merge_rank_results. Default off (no behaviour change).
    lexical: re-score by token overlap on title+excerpt plus original retrieval score.
    """
    mode = rerank_mode()
    if mode in ("", "off", "none", "0", "false", "no"):
        return merged[:limit]
    if mode != "lexical":
        return merged[:limit]
    q = (query or "").strip()
    if not q:
        return merged[:limit]
    terms = tokenize(q)
    if not terms:
        return merged[:limit]
    weight = float((os.environ.get("HATORI_RERANK_LEXICAL_WEIGHT") or "3.0").strip() or "3.0")
    ranked: list[tuple[float, float, int, dict]] = []
    for idx, item in enumerate(merged):
        hay = f"{item.get('title') or ''} {(item.get('excerpt') or '')}"
        ov = float(score_text(hay, terms))
        base = float(item.get("score", 0.0))
        combined = weight * ov + base
        ranked.append((-combined, -base, idx, item))
    ranked.sort()
    return [t[3] for t in ranked[:limit]]


def ask_runtime(question: str, allow_pending: bool = False, done_signal: bool = False) -> dict:
    current_connectivity = connectivity_state()
    classification = classify_request(question)

    pks_hits = retrieve_pks(question, allow_pending=allow_pending, limit=6)
    emb_kw_hits = retrieve_embeddings(question, limit=6)
    emb_sem_hits = retrieve_embeddings_semantic(question, limit=6)
    merged = merge_rank_results(pks_hits + emb_kw_hits + emb_sem_hits, limit=6)
    merged = rerank_merged_results(question, merged, 6)

    evidence = merged
    if evidence:
        lines = [
            "Using local offline evidence, these are the most relevant records:",
        ]
        for item in evidence[:3]:
            lines.append(f"- [{item['citation']}] {item['excerpt']}")
        answer = "\n".join(lines)
    else:
        answer = (
            "I cannot answer this confidently from local approved knowledge yet. "
            "Please ingest relevant documents or add an approved PKS record first."
        )

    assumptions = [
        "Unconfirmed (offline): no web or third-party live sources were used.",
        "Only local PKS and local artefact chunks were considered.",
    ]

    if evidence:
        next_actions = [
            "Review the cited local records.",
            "If needed, promote/update PKS entries through Pending -> Approved governance.",
            "If evidence is incomplete, ingest additional local artefacts.",
        ]
    else:
        next_actions = [
            "Ingest a local document with hatori ingest <path>.",
            "Add or approve a PKS fact/decision entry relevant to this question.",
            "Re-run hatori ask after local evidence exists.",
        ]

    memory_patch = "No memory changes."

    user_event_id = insert_interaction(
        role="user",
        content=question,
        meta={"source": "cli.ask", "classification": classification, "connectivity": current_connectivity},
    )

    learning_log = "No learning event recorded."
    learning_event_id = None
    if done_signal:
        learning_event_id = insert_learning(
            kind="ImplicitPositive",
            confidence="Low",
            details={"source": "cli.ask", "rule": "done_signal", "question": question},
            interaction_id=user_event_id,
        )
        learning_log = f"Recorded ImplicitPositive (Low) as learning event {learning_event_id}."

    payload = {
        "connectivity_state": current_connectivity,
        "classification": classification,
        "answer": answer,
        "evidence": evidence,
        "assumptions": assumptions,
        "next_actions": next_actions,
        "memory_patch": memory_patch,
        "learning_log": learning_log,
        "interaction_user_id": user_event_id,
        "interaction_agent_id": None,
        "learning_event_id": learning_event_id,
        "model_adapter": os.environ.get("HATORI_MODEL", "none").strip().lower() or "none",
        "model_draft": "",
    }

    model = get_model_adapter()
    system_prompt = build_system_prompt()
    task_prompt = build_task_prompt(
        user_text=question,
        connectivity=current_connectivity,
        retrieved_context={
            "classification": classification,
            "evidence": evidence[:6],
            "assumptions": assumptions,
        },
    )
    try:
        model_draft = model.generate(system_prompt=system_prompt, task_prompt=task_prompt)
    except Exception as exc:
        model_draft = f"Model unavailable: {exc}"
    payload["model_adapter"] = model.name
    payload["model_draft"] = model_draft

    rendered = render_default_output(payload)
    agent_event_id = insert_interaction(
        role="agent",
        content=rendered,
        meta={
            "source": "cli.ask",
            "classification": classification,
            "connectivity": current_connectivity,
            "evidence_count": len(evidence),
            "citations": [e["citation"] for e in evidence],
            "model": model.name,
        },
    )
    payload["interaction_agent_id"] = agent_event_id
    return payload


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


def read_file_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception:
            raise RuntimeError("PDF ingestion requires pypdf (install in current environment).")
        reader = PdfReader(str(path))
        pages = [(p.extract_text() or "") for p in reader.pages]
        return "\n".join(pages)

    # Best-effort text read for local/offline ingestion.
    return path.read_text(encoding="utf-8", errors="ignore")


def iter_source_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted([p for p in path.rglob("*") if p.is_file()])
    raise SystemExit(f"Path does not exist: {path}")


def ingest(path_str: str) -> dict:
    target = Path(path_str).expanduser().resolve()
    files = iter_source_files(target)
    if not files:
        raise SystemExit("No files found to ingest.")

    artefacts_created = 0
    chunks_created = 0
    skipped: list[dict] = []
    ingested: list[dict] = []
    adapter = embedding_adapter()

    skip_ext = {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".zip", ".gz", ".tar", ".tgz", ".7z", ".mp3",
        ".mp4", ".mov", ".avi", ".sqlite", ".db", ".pyc", ".so", ".dylib"
    }

    for fpath in files:
        if fpath.suffix.lower() in skip_ext:
            skipped.append({"path": str(fpath), "reason": "Unsupported binary extension"})
            continue

        try:
            raw = fpath.read_bytes()
            text = read_file_text(fpath)
        except Exception as exc:
            skipped.append({"path": str(fpath), "reason": str(exc)})
            continue

        chunks = chunk_text(text)
        if not chunks:
            skipped.append({"path": str(fpath), "reason": "No extractable text"})
            continue

        artefact_id = str(uuid.uuid4())
        sha = hashlib.sha256(raw).hexdigest()
        media_type, _ = mimetypes.guess_type(str(fpath))
        meta = {"source": "cli.ingest", "path": str(fpath), "chunk_count": len(chunks)}
        media_sql = "NULL" if media_type is None else f"'{_esc_sql(media_type)}'"

        psql(
            "INSERT INTO artefacts (id, kind, uri, title, media_type, sha256, metadata) "
            f"VALUES ('{artefact_id}', 'file', '{_esc_sql(str(fpath))}', '{_esc_sql(fpath.name)}', "
            f"{media_sql}, '{sha}', '{_esc_sql(json.dumps(meta, ensure_ascii=False))}'::jsonb);"
        )
        audit("ingest", "artefact", artefact_id, {"path": str(fpath), "chunks": len(chunks)})
        artefacts_created += 1

        vectors = adapter.embed(chunks)
        for i, chunk in enumerate(chunks):
            emb_id = str(uuid.uuid4())
            chunk_id = f"{artefact_id}:{i}"
            cmeta = {
                "source": "cli.ingest",
                "index": i,
                "path": str(fpath),
                "embedder": adapter.name,
                "embed_dim": adapter.dimension,
            }
            emb_sql = _esc_sql(vector_sql_literal(vectors[i]))
            psql(
                "INSERT INTO embeddings (id, artefact_id, chunk_id, content, embedding, metadata) "
                f"VALUES (\x27{emb_id}\x27, \x27{artefact_id}\x27, \x27{_esc_sql(chunk_id)}\x27, "
                f"\x27{_esc_sql(chunk)}\x27, \x27{emb_sql}\x27::vector, "
                f"\x27{_esc_sql(json.dumps(cmeta, ensure_ascii=False))}\x27::jsonb);"
            )
            chunks_created += 1

        ingested.append({"path": str(fpath), "artefact_id": artefact_id, "chunks": len(chunks)})

    payload = {
        "target": str(target),
        "files_scanned": len(files),
        "artefacts_created": artefacts_created,
        "chunks_created": chunks_created,
        "ingested": ingested,
        "skipped": skipped,
    }
    return payload


def search_runtime(query: str, limit: int, allow_pending: bool) -> dict:
    pks_hits = retrieve_pks(query, allow_pending=allow_pending, limit=limit)
    emb_kw_hits = retrieve_embeddings(query, limit=limit)
    emb_sem_hits = retrieve_embeddings_semantic(query, limit=limit)
    merged = merge_rank_results(pks_hits + emb_kw_hits + emb_sem_hits, limit=limit)
    merged = rerank_merged_results(query, merged, limit)
    return {
        "query": query,
        "limit": limit,
        "results": merged,
    }


def _contains_pending_guards() -> bool:
    source = Path(__file__).read_text(encoding="utf-8")
    return 'statuses = ["Approved"]' in source and "if allow_pending:" in source


def consistency_check(subset: int = 8) -> dict:
    state = connectivity_state()

    profile_rows = psql_json(
        "SELECT id, module, status, title FROM pks_records "
        "WHERE module IN ('A','C') AND status IN ('Approved','Pending') "
        "ORDER BY updated_at DESC LIMIT 10"
    )
    project_rows = psql_json(
        "SELECT id, module, status, title FROM pks_records "
        "WHERE module IN ('D','E') AND status IN ('Approved','Pending') "
        "ORDER BY updated_at DESC LIMIT 10"
    )
    contested_rows = psql_json(
        "SELECT id, module, status, title FROM pks_records "
        "WHERE status='Contested' ORDER BY updated_at DESC LIMIT 10"
    )

    auto_write_violations = psql_json(
        "SELECT id, occurred_at, actor, action, target_type, target_id, details "
        "FROM audit_events "
        "WHERE actor='agent' "
        "AND target_type='pks_record' "
        "AND COALESCE(details->>'auto_capture','false')='true' "
        "AND COALESCE(details->>'explicit_instruction','false')!='true' "
        "ORDER BY occurred_at DESC LIMIT 20"
    )
    pending_rule_present = _contains_pending_guards()

    subset = max(1, int(subset))
    golden_cmd = [sys.executable, "tests/golden/run_golden.py", "--subset", str(subset)]
    golden_proc = subprocess.run(golden_cmd, capture_output=True, text=True)
    golden_pass = golden_proc.returncode == 0

    checks = [
        {
            "name": "no_auto_writes_to_A_H_without_explicit_instruction",
            "ok": len(auto_write_violations) == 0,
            "violations": auto_write_violations,
        },
        {
            "name": "pending_exclusion_rules_present",
            "ok": pending_rule_present,
            "details": "retrieve_pks keeps Approved-only unless --allow-pending",
        },
        {
            "name": "golden_subset",
            "ok": golden_pass,
            "details": {"subset": subset, "cmd": " ".join(golden_cmd)},
            "stdout_tail": "\n".join((golden_proc.stdout or "").strip().splitlines()[-8:]),
            "stderr_tail": "\n".join((golden_proc.stderr or "").strip().splitlines()[-8:]),
        },
    ]
    ok = all(c["ok"] for c in checks)
    return {
        "ok": ok,
        "connectivity_state": state,
        "summary": {
            "profile_preferences_count": len(profile_rows),
            "active_projects_tasks_count": len(project_rows),
            "contested_count": len(contested_rows),
            "profile_preferences": profile_rows,
            "active_projects_tasks": project_rows,
            "contested_records": contested_rows,
        },
        "checks": checks,
    }


def print_consistency_check(payload: dict) -> None:
    status = "PASS" if payload["ok"] else "FAIL"
    summary = payload["summary"]
    print(f"Consistency Check: {status}")
    print(f"Connectivity State: {payload['connectivity_state']}")
    print(
        f"PKS Summary: profile/preferences={summary['profile_preferences_count']} "
        f"projects/tasks={summary['active_projects_tasks_count']} contested={summary['contested_count']}"
    )
    for check in payload["checks"]:
        marker = "OK" if check["ok"] else "FAIL"
        print(f"- {marker}: {check['name']}")
    golden = next((c for c in payload["checks"] if c["name"] == "golden_subset"), None)
    if golden:
        tail = golden.get("stdout_tail", "")
        if tail:
            print("Golden subset tail:")
            print(tail)


def parse_bool_flag(args: list[str], flag: str) -> tuple[bool, list[str]]:
    found = flag in args
    if not found:
        return False, args
    return True, [a for a in args if a != flag]


def parse_int_option(args: list[str], name: str, default: int) -> tuple[int, list[str]]:
    if name not in args:
        return default, args
    i = args.index(name)
    if i + 1 >= len(args):
        raise SystemExit(f"{name} requires a numeric value")
    value = int(args[i + 1])
    cleaned = args[:i] + args[i + 2 :]
    return value, cleaned


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        raise SystemExit("Usage: hatori <ping|log|feedback|pks|ask|ingest|search|consistency-check|model-smoke> ...")

    cmd = argv[1]

    if cmd == "ping":
        ping()
        return

    if cmd == "log":
        if len(argv) < 4:
            raise SystemExit("Usage: hatori log <role> <content>")
        log(argv[2], " ".join(argv[3:]), {"source": "cli"})
        return

    if cmd == "feedback":
        if len(argv) >= 3 and argv[2] == "--last":
            if len(argv) < 6:
                raise SystemExit("Usage: hatori feedback --last <kind> <confidence> <details_json>")
            iid = last_interaction_id()
            if not iid:
                raise SystemExit("No interactions found.")
            feedback(argv[3], argv[4], json.loads(argv[5]), iid)
            return
        if len(argv) < 5:
            raise SystemExit("Usage: hatori feedback <kind> <confidence> <details_json> [interaction_id]")
        iid = argv[5] if len(argv) >= 6 else None
        feedback(argv[2], argv[3], json.loads(argv[4]), iid)
        return

    if cmd == "pks":
        if len(argv) < 3:
            raise SystemExit("Usage: hatori pks <add|list|show|approve|deprecate|contest> ...")
        sub = argv[2]
        if sub == "add":
            if len(argv) < 6:
                raise SystemExit("Usage: hatori pks add <module> <title> <body> [--status Pending|Approved|Deprecated|Contested]")
            status = None
            if "--status" in argv:
                i = argv.index("--status")
                if i + 1 >= len(argv):
                    raise SystemExit("--status requires value")
                status = argv[i + 1]
            pks_add(argv[3], argv[4], argv[5], status)
            return

        if sub == "list":
            module = None
            status = None
            limit = 20
            i = 3
            while i < len(argv):
                if argv[i] == "--module":
                    module = argv[i + 1]
                    i += 2
                    continue
                if argv[i] == "--status":
                    status = argv[i + 1]
                    i += 2
                    continue
                if argv[i] == "--limit":
                    limit = int(argv[i + 1])
                    i += 2
                    continue
                raise SystemExit("Unknown option: " + argv[i])
            pks_list(module, status, limit)
            return

        if sub == "show":
            if len(argv) < 4:
                raise SystemExit("Usage: hatori pks show <uuid>")
            pks_show(argv[3])
            return

        if sub == "approve":
            if len(argv) < 4:
                raise SystemExit("Usage: hatori pks approve <uuid>")
            pks_set_status(argv[3], "Approved")
            return

        if sub == "deprecate":
            if len(argv) < 4:
                raise SystemExit("Usage: hatori pks deprecate <uuid>")
            pks_set_status(argv[3], "Deprecated")
            return

        if sub == "contest":
            if len(argv) < 5:
                raise SystemExit("Usage: hatori pks contest <uuid> <reason_json>")
            pks_set_status(argv[3], "Contested", json.loads(argv[4]))
            return

        raise SystemExit("Unknown pks subcommand: " + sub)

    if cmd == "propose-pks":
        args = argv[2:]
        json_mode, args = parse_bool_flag(args, "--json")
        if len(args) != 1:
            raise SystemExit("Usage: hatori propose-pks <path|artefact_id> [--json]")
        payload = propose_pks_from_doc(args[0])
        if json_mode:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            if payload.get("error"):
                print("Error:", payload["error"])
            print(f"Proposed {payload['proposed']} PKS record(s) (Pending). IDs: {payload.get('ids', [])}")
        return

    if cmd == "ask":
        args = argv[2:]
        json_mode, args = parse_bool_flag(args, "--json")
        allow_pending, args = parse_bool_flag(args, "--allow-pending")
        done_signal, args = parse_bool_flag(args, "--done")
        question = " ".join(args).strip()
        if not question:
            raise SystemExit("Usage: hatori ask <question> [--allow-pending] [--done] [--json]")

        payload = ask_runtime(question, allow_pending=allow_pending, done_signal=done_signal)
        if json_mode:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_default_output(payload))
        return

    if cmd == "ingest":
        args = argv[2:]
        json_mode, args = parse_bool_flag(args, "--json")
        if len(args) != 1:
            raise SystemExit("Usage: hatori ingest <path> [--json]")
        payload = ingest(args[0])
        if json_mode:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"Ingest complete. scanned={payload['files_scanned']} artefacts={payload['artefacts_created']} "
                f"chunks={payload['chunks_created']} skipped={len(payload['skipped'])}"
            )
        return

    if cmd == "search":
        args = argv[2:]
        json_mode, args = parse_bool_flag(args, "--json")
        allow_pending, args = parse_bool_flag(args, "--allow-pending")
        limit, args = parse_int_option(args, "--limit", 5)
        query = " ".join(args).strip()
        if not query:
            raise SystemExit("Usage: hatori search <query> [--limit N] [--allow-pending] [--json]")

        payload = search_runtime(query, limit=limit, allow_pending=allow_pending)
        if json_mode:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Query: {payload['query']}")
            if not payload["results"]:
                print("No local matches.")
            else:
                for row in payload["results"]:
                    print(f"- [{row['citation']}] score={row['score']} title={row['title']}")
                    print(f"  excerpt={row['excerpt']}")
                    if row.get("artefact_id"):
                        print(f"  artefact_id={row['artefact_id']} provenance={row.get('provenance', 'unknown')}")
        return

    if cmd == "consistency-check":
        args = argv[2:]
        json_mode, args = parse_bool_flag(args, "--json")
        subset, args = parse_int_option(args, "--subset", 8)
        if args:
            raise SystemExit("Usage: hatori consistency-check [--subset N] [--json]")
        payload = consistency_check(subset=subset)
        if json_mode:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_consistency_check(payload)
        if not payload["ok"]:
            raise SystemExit(1)
        return

    if cmd == "model-smoke":
        args = argv[2:]
        prompt = " ".join(args).strip() or "Say OK in one short line."
        model = get_model_adapter()
        system_prompt = build_system_prompt()
        task_prompt = build_task_prompt(
            user_text=prompt,
            connectivity=connectivity_state(),
            retrieved_context={"mode": "smoke"},
        )
        health = model.healthcheck()
        if not health.get("ok", False):
            raise SystemExit(f"Model healthcheck failed: {json.dumps(health, ensure_ascii=False)}")
        out = model.generate(system_prompt=system_prompt, task_prompt=task_prompt)
        print(out)
        return

    raise SystemExit("Unknown command: " + cmd)


if __name__ == "__main__":
    main(sys.argv)
