"""
PKS (Personal Knowledge System) module — implementation of docs/10-api-contracts/interfaces.md.
Writes to module I (interactions), module J (learning), and PKS records A–H.
"""
import uuid
from typing import Any

from hatori import db

_UUID_RE = __import__("re").compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def append_interaction(event: dict[str, Any]) -> str:
    """Append to module I (append-only). event: role, content, metadata; optional session_id."""
    role = (event.get("role") or "user").strip()
    content = (event.get("content") or "").strip()
    metadata = event.get("metadata") or {}
    session_id = event.get("session_id")
    iid = str(uuid.uuid4())
    meta_json = db.jsonb_sql_literal(metadata)
    sid_sql = f"'{db.esc_sql(session_id)}'" if session_id else "NULL"
    sql = (
        "INSERT INTO interaction_events (id, session_id, role, content, metadata) "
        f"VALUES ('{iid}', {sid_sql}, '{db.esc_sql(role)}', '{db.esc_sql(content)}', {meta_json});"
    )
    db.run_psql(sql)
    return iid


def log_learning(signal: dict[str, Any]) -> str:
    """Write to module J. signal: kind, confidence, details; optional related_interaction_id."""
    kind = (signal.get("kind") or "Other").strip()
    confidence = (signal.get("confidence") or "Low").strip()
    details = signal.get("details") or {}
    related = signal.get("related_interaction_id")
    lid = str(uuid.uuid4())
    det_json = db.jsonb_sql_literal(details)
    if related:
        if not _UUID_RE.match(related):
            raise ValueError("related_interaction_id must be a UUID")
        sql = (
            "INSERT INTO learning_events (id, kind, confidence, details, related_interaction_id) "
            f"VALUES ('{lid}', '{db.esc_sql(kind)}', '{db.esc_sql(confidence)}', {det_json}, '{db.esc_sql(related)}');"
        )
    else:
        sql = (
            "INSERT INTO learning_events (id, kind, confidence, details) "
            f"VALUES ('{lid}', '{db.esc_sql(kind)}', '{db.esc_sql(confidence)}', {det_json});"
        )
    db.run_psql(sql)
    return lid


def write_pending(module: str, record: dict[str, Any]) -> str:
    """Insert Pending entry in A–H. record: title, body; optional scope, tags."""
    mod = (module or "A").strip().upper()
    if len(mod) != 1 or mod not in "ABCDEFGH":
        raise ValueError("module must be one of A–H")
    title = (record.get("title") or "").strip()[:500]
    body = (record.get("body") or "").strip()[:8000]
    if not title or not body:
        raise ValueError("title and body required")
    scope = (record.get("scope") or "Personal").strip()[:200]
    rid = str(uuid.uuid4())
    sql = (
        "INSERT INTO pks_records (id, module, title, body, status, provenance, confidence, scope) "
        f"VALUES ('{rid}', '{db.esc_sql(mod)}', '{db.esc_sql(title)}', '{db.esc_sql(body)}', "
        f"'Pending', 'LocalDoc', 'Medium', '{db.esc_sql(scope)}');"
    )
    db.run_psql(sql)
    _audit("create", "pks_record", rid, {"status": "Pending", "module": mod})
    return rid


def approve(record_id: str) -> None:
    """Set status to Approved and audit."""
    if not _UUID_RE.match(record_id):
        raise ValueError("record_id must be a UUID")
    db.run_psql(f"UPDATE pks_records SET status='Approved', updated_at=now() WHERE id='{db.esc_sql(record_id)}';")
    _audit("approve", "pks_record", record_id, {"status": "Approved"})


def deprecate(record_id: str) -> None:
    """Set status to Deprecated and audit."""
    if not _UUID_RE.match(record_id):
        raise ValueError("record_id must be a UUID")
    db.run_psql(f"UPDATE pks_records SET status='Deprecated', updated_at=now() WHERE id='{db.esc_sql(record_id)}';")
    _audit("deprecate", "pks_record", record_id, {"status": "Deprecated"})


def redact(record_id: str) -> None:
    """Set status to Deprecated (redact semantics) and audit."""
    if not _UUID_RE.match(record_id):
        raise ValueError("record_id must be a UUID")
    db.run_psql(f"UPDATE pks_records SET status='Deprecated', updated_at=now() WHERE id='{db.esc_sql(record_id)}';")
    _audit("redact", "pks_record", record_id, {"status": "Deprecated"})


def query(filters: dict[str, Any] | None = None) -> list[dict]:
    """Return records with provenance, confidence, status. filters: status, module, limit."""
    filters = filters or {}
    statuses = filters.get("status")
    if statuses is None:
        statuses = ["Approved"]
    if isinstance(statuses, str):
        statuses = [statuses]
    status_sql = ",".join(f"'{db.esc_sql(s)}'" for s in statuses)
    where = [f"status IN ({status_sql})"]
    module = filters.get("module")
    if module:
        where.append(f"module='{db.esc_sql(module)}'")
    limit = min(int(filters.get("limit", 400)), 500)
    sql = (
        "SELECT id, module, status, title, body, provenance, confidence, scope, updated_at "
        f"FROM pks_records WHERE {' AND '.join(where)} ORDER BY updated_at DESC LIMIT {limit}"
    )
    return db.run_psql_json(sql)


def _audit(action: str, target_type: str, target_id: str, details: dict) -> None:
    db.run_psql(
        "INSERT INTO audit_events (id, actor, action, target_type, target_id, details) "
        f"VALUES (gen_random_uuid(), 'hatori.pks', '{db.esc_sql(action)}', "
        f"'{db.esc_sql(target_type)}', '{db.esc_sql(target_id)}', {db.jsonb_sql_literal(details)});"
    )
