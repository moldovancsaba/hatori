"""
RAG (retrieval and indexing) — implementation of docs/10-api-contracts/interfaces.md.
index_document, search_local, get_sources.
"""
from pathlib import Path
from typing import Any

from hatori import db


def index_document(path: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Chunk, embed, and store a document. path: file path; metadata: optional.
    Returns artefact_id, chunks_created, etc.
    """
    from hatori.cli import ingest  # defer to avoid circular import at module load

    try:
        result = ingest(path)
    except SystemExit as e:
        return {"artefact_id": None, "chunks_created": 0, "error": str(e)}
    ingested = result.get("ingested") or []
    if not ingested:
        return {
            "artefact_id": None,
            "chunks_created": 0,
            "error": result.get("skipped", [{}])[0].get("reason", "No files ingested") if result.get("skipped") else "No files ingested",
        }
    first = ingested[0]
    return {
        "artefact_id": first.get("artefact_id"),
        "chunks_created": first.get("chunks", 0),
        "path": first.get("path"),
    }


def search_local(query: str, k: int = 5, filters: dict[str, Any] | None = None) -> list[dict]:
    """
    Search local PKS + embeddings; return passages with provenance.
    filters: allow_pending (bool), etc.
    """
    from hatori.cli import search_runtime  # defer to avoid circular import

    f = filters or {}
    allow_pending = f.get("allow_pending", False)
    limit = min(max(1, k), 20)
    result = search_runtime(query=query, limit=limit, allow_pending=allow_pending)
    return result.get("results") or []


def get_sources(source_ids: list[str]) -> list[dict]:
    """Return artefacts for citations by id (artefact UUIDs or pks:uuid / emb:id refs)."""
    if not source_ids:
        return []
    # Normalize: accept raw UUIDs or prefixed (we only resolve artefact ids here)
    ids: list[str] = []
    for sid in source_ids:
        s = (sid or "").strip()
        if not s:
            continue
        if s.startswith("emb:") and ":" in s[4:]:
            # emb:artefact_id:chunk_idx -> use artefact_id
            parts = s[4:].split(":", 1)
            if parts and parts[0] not in ids:
                ids.append(parts[0])
        elif s.startswith("pks:"):
            # PKS records are not in artefacts; skip or could join pks_records
            continue
        else:
            if s not in ids:
                ids.append(s)
    if not ids:
        return []
    escaped = ",".join(f"'{db.esc_sql(i)}'" for i in ids)
    rows = db.run_psql_json(
        f"SELECT id, kind, uri, title, metadata FROM artefacts WHERE id IN ({escaped})"
    )
    return rows
