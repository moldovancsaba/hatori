import json
import os
import ipaddress
import uuid
import mimetypes
import hashlib
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from collections import defaultdict
from collections import deque

from fastapi import FastAPI
from fastapi import File
from fastapi import Form
from fastapi import Header
from fastapi import HTTPException
from fastapi import UploadFile
from pydantic import BaseModel
from pydantic import Field

from hatori.embeddings import get_embeddings_adapter
from hatori.model import MlxAdapter
from hatori.model import OllamaAdapter
from hatori.model import get_task_model_adapter
import ui.app as ui

ROOT_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT_DIR / "VERSION"
INGEST_API_DIR = ROOT_DIR / "artefacts" / "ingest_api"
UPLOADS_API_DIR = ROOT_DIR / "artefacts" / "uploads_api"
app = FastAPI(title="{hatori} API", version=VERSION_FILE.read_text(encoding="utf-8").strip())


def _validate_bind_policy() -> None:
    bind = (os.environ.get("HATORI_API_BIND") or "127.0.0.1").strip()
    if not bind:
        bind = "127.0.0.1"
    if bind in {"localhost", "::1"}:
        return
    try:
        ip = ipaddress.ip_address(bind)
        is_loopback = ip.is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback and not (os.environ.get("HATORI_API_ALLOW_CIDRS") or "").strip():
        raise RuntimeError("Refusing non-loopback HATORI_API_BIND without HATORI_API_ALLOW_CIDRS")


_validate_bind_policy()


def require_token(x_hatori_token: str | None = Header(default=None, alias="X-Hatori-Token")) -> None:
    expected = (os.environ.get("HATORI_API_TOKEN") or "").strip()
    if not expected or x_hatori_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


class _RateLimiter:
    def __init__(self) -> None:
        self.window_s = 60.0
        self._lock = threading.Lock()
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def hit(self, endpoint: str, token: str, limit: int) -> None:
        now = time.time()
        key = (endpoint, token)
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= limit:
                raise HTTPException(status_code=429, detail="rate_limited")
            q.append(now)

    def counts_last_minute(self) -> dict[str, int]:
        now = time.time()
        out: dict[str, int] = {}
        with self._lock:
            for (endpoint, _token), q in self._hits.items():
                while q and now - q[0] > self.window_s:
                    q.popleft()
                out[endpoint] = out.get(endpoint, 0) + len(q)
        return out


_RATE_LIMITER = _RateLimiter()


def _require_token_value(x_hatori_token: str | None) -> str:
    expected = (os.environ.get("HATORI_API_TOKEN") or "").strip()
    if not expected or x_hatori_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")
    return x_hatori_token


def _enforce_rate(endpoint: str, token: str) -> None:
    limits = {
        "respond": int((os.environ.get("HATORI_RL_RESPOND_PER_MIN") or "30").strip()),
        "ingest": int((os.environ.get("HATORI_RL_INGEST_PER_MIN") or "120").strip()),
        "outcome": int((os.environ.get("HATORI_RL_OUTCOME_PER_MIN") or "120").strip()),
    }
    _RATE_LIMITER.hit(endpoint=endpoint, token=token, limit=limits[endpoint])


def _model_status() -> tuple[str, str]:
    explicit = (os.environ.get("HATORI_MODEL") or "").strip().lower()
    if explicit:
        if explicit == "ollama":
            return "ollama", (os.environ.get("HATORI_OLLAMA_MODEL") or "llama3.2:3b").strip()
        return explicit, ""
    if ui.prefer_ollama_if_available():
        return "ollama", (os.environ.get("HATORI_OLLAMA_MODEL") or "llama3.2:3b").strip()
    return "none", ""


def _compact_runtime_health(raw: dict[str, Any], backend: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "backend": backend,
        "ok": bool(raw.get("ok")),
        "model": (raw.get("model") or "").strip() if isinstance(raw.get("model"), str) else "",
        "model_available": raw.get("model_available"),
        "error": (raw.get("error") or "").strip() if isinstance(raw.get("error"), str) else "",
    }
    if "configured" in raw:
        out["configured"] = bool(raw.get("configured"))
    return out


def _runtime_status() -> dict[str, Any]:
    mlx_model = (os.environ.get("HATORI_MLX_MODEL") or "").strip()
    mlx_disabled = (os.environ.get("HATORI_DISABLE_MLX") or "").strip() == "1"
    if not mlx_model or mlx_disabled:
        mlx = {"ok": False, "adapter": "mlx", "configured": False, "error": "not configured" if not mlx_model else "disabled by HATORI_DISABLE_MLX"}
    else:
        mlx = MlxAdapter(model=mlx_model).healthcheck()
        mlx["configured"] = True
    ollama = OllamaAdapter(timeout=2).healthcheck()
    ollama["configured"] = True
    return {
        "mlx": _compact_runtime_health(mlx, "mlx"),
        "ollama": _compact_runtime_health(ollama, "ollama"),
    }


def _task_routing_status() -> dict[str, Any]:
    lane_map = {
        "writer": "reply_write",
        "drafter": "context_pack",
        "judge": "answer_score",
    }
    out: dict[str, Any] = {}
    for lane, task in lane_map.items():
        adapter, err, meta = get_task_model_adapter(task)
        backend_used = (meta or {}).get("backend_used") if isinstance(meta, dict) else None
        model_used = (meta or {}).get("model_used") if isinstance(meta, dict) else None
        route = (meta or {}).get("route") if isinstance(meta, dict) else None
        out[lane] = {
            "task": task,
            "ok": adapter is not None,
            "backend": backend_used or (adapter.name if adapter is not None else "none"),
            "model": model_used or (getattr(adapter, "model", "") if adapter is not None else ""),
            "fallback_used": bool((meta or {}).get("fallback_used")) if isinstance(meta, dict) else False,
            "error": (err or "").strip(),
            "route": route if isinstance(route, dict) else {},
        }
    return out


def _conversation_id(value: str | None) -> str:
    raw = (value or "").strip()
    return raw if raw else f"reply:{uuid.uuid4()}"


class RespondBody(BaseModel):
    conversation_id: str = ""
    message_id: str = ""
    sender_id: str = ""
    message: str
    received_at: str | None = None
    mode: str = "chat"
    external_request_id: str | None = None
    thread_context: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackBody(BaseModel):
    assistant_interaction_id: str
    vote: str
    category: str = "Other"
    comment: str = ""
    external_request_id: str | None = None


class OutcomeBody(BaseModel):
    external_outcome_id: str
    assistant_interaction_id: str
    conversation_id: str | None = None
    platform: str = "other"
    recipient_id: str | None = None
    status: str
    original_text: str | None = None
    final_sent_text: str | None = None
    diff: str | None = None
    edit_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestBody(BaseModel):
    external_event_id: str | None = None
    event_id: str | None = None
    kind: str
    conversation_id: str | None = None
    sender_id: str | None = None
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestPathBody(BaseModel):
    external_event_id: str
    kind: str
    path: str
    sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _detect_media_type(path: Path) -> str:
    guessed, _enc = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _is_chunkable_text(path: Path, media_type: str) -> bool:
    suffix = path.suffix.lower()
    return suffix in {".txt", ".md"} or media_type.startswith("text/")


def _insert_embeddings_from_text(artefact_id: str, text: str, meta_base: dict[str, Any]) -> int:
    chunks = ui.chunk_text(text)
    if not chunks:
        return 0
    adapter = get_embeddings_adapter()
    vectors = adapter.embed(chunks)
    created = 0
    for idx, chunk in enumerate(chunks):
        emb_id = str(uuid.uuid4())
        chunk_id = f"{artefact_id}:{idx}"
        emb_sql = ui._esc_sql(ui.vector_sql_literal(vectors[idx]))
        cmeta = {
            **meta_base,
            "index": idx,
            "embedder": adapter.name,
            "embed_dim": adapter.dimension,
        }
        ui.psql(
            "INSERT INTO embeddings (id, artefact_id, chunk_id, content, embedding, metadata) "
            f"VALUES ('{emb_id}', '{artefact_id}', '{ui._esc_sql(chunk_id)}', '{ui._esc_sql(chunk)}', "
            f"'{emb_sql}'::vector, '{ui._esc_sql(json.dumps(cmeta, ensure_ascii=False))}'::jsonb);"
        )
        created += 1
    return created


def _parse_metadata_json(raw: str | None) -> dict[str, Any]:
    txt = (raw or "").strip()
    if not txt:
        return {}
    try:
        parsed = json.loads(txt)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid metadata JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    return parsed


def _artifact_id_by_external_event_id(external_event_id: str, source: str) -> str:
    return ui.psql(
        "SELECT id FROM artefacts "
        f"WHERE COALESCE(metadata->>'external_event_id','')='{ui._esc_sql(external_event_id)}' "
        f"AND COALESCE(metadata->>'source','')='{ui._esc_sql(source)}' "
        "ORDER BY created_at DESC LIMIT 1;"
    ).strip()


def _interaction_id_by_external_event_id(external_event_id: str, source: str) -> str:
    return ui.psql(
        "SELECT id FROM interaction_events "
        f"WHERE COALESCE(metadata->>'external_event_id','')='{ui._esc_sql(external_event_id)}' "
        f"AND COALESCE(metadata->>'source','')='{ui._esc_sql(source)}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    ).strip()


def _delivery_event_id_by_external_outcome_id(external_outcome_id: str) -> str:
    return ui.psql(
        "SELECT id FROM delivery_events "
        f"WHERE external_outcome_id='{ui._esc_sql(external_outcome_id)}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    ).strip()


def _ingest_file_to_artefact(
    *,
    source: str,
    external_event_id: str,
    kind: str,
    file_path: Path,
    media_type: str,
    provided_sha256: str | None,
    conversation_id: str | None,
    sender_id: str | None,
    metadata: dict[str, Any],
) -> tuple[str, str, int]:
    sha = _sha256_file(file_path)
    if provided_sha256 and provided_sha256.strip().lower() != sha:
        raise HTTPException(status_code=400, detail="sha256 mismatch")
    artefact_id = str(uuid.uuid4())
    merged_meta = {
        "source": source,
        "external_event_id": external_event_id,
        "kind": kind,
        "conversation_id": conversation_id or "",
        "sender_id": sender_id or "",
        "byte_size": file_path.stat().st_size,
        **(metadata or {}),
    }
    ui.psql(
        "INSERT INTO artefacts (id, kind, uri, title, media_type, sha256, metadata) "
        f"VALUES ('{artefact_id}', 'file', '{ui._esc_sql(str(file_path))}', '{ui._esc_sql(file_path.name)}', "
        f"'{ui._esc_sql(media_type)}', '{sha}', '{ui._esc_sql(json.dumps(merged_meta, ensure_ascii=False))}'::jsonb);"
    )
    chunks_created = 0
    if _is_chunkable_text(file_path, media_type):
        text = file_path.read_text(encoding="utf-8", errors="replace")
        chunks_created = _insert_embeddings_from_text(
            artefact_id=artefact_id,
            text=text,
            meta_base={
                "source": source,
                "external_event_id": external_event_id,
                "kind": kind,
                "media_type": media_type,
            },
        )
    return artefact_id, sha, chunks_created


def _path_allowed(path: Path) -> bool:
    allow_raw = (os.environ.get("HATORI_PATH_ALLOWLIST") or "").strip()
    if not allow_raw:
        return False
    try:
        resolved = path.resolve(strict=False)
    except Exception:
        return False
    for item in allow_raw.split(","):
        base_raw = item.strip()
        if not base_raw:
            continue
        try:
            base = Path(base_raw).expanduser().resolve(strict=False)
        except Exception:
            continue
        if resolved == base or base in resolved.parents:
            return True
    return False


def _deterministic_reply_fallback(language_code: str, message: str) -> str:
    lowered = (message or "").lower()
    asks_for_draft = any(
        marker in lowered
        for marker in [
            "draft",
            "write",
            "message",
            "follow-up",
            "follow up",
            "email",
            "reply",
            "iras",
            "irj",
            "uzenet",
            "kovetes",
        ]
    )
    if language_code == "hu":
        if asks_for_draft:
            return (
                "Persze. Itt egy rovid uzenetjavaslat:\n"
                "Szia! Egy gyors kovetes: nehany napja kuldtem egy uzenetet, "
                "es csak szeretnek roviden rakerdezni, hogy van-e frissites. "
                "Nem surgos, amikor idod engedi, orulnek egy valasznak. Koszonom!"
            )
        return "Rendben, segitek. Ird meg egy mondatban, pontosan milyen valaszt szeretnel, es adok egy rovid, kuldheto szoveget."
    if asks_for_draft:
        return (
            "Sure. Here is a short message you can send:\n"
            "Hi, just following up on my previous message from a few days ago. "
            "No rush, but I would appreciate a quick update when you have a moment. Thanks!"
        )
    return "Sure, I can help with that. Share the exact context in one sentence and I will provide a short send-ready draft."


def _is_model_unavailable_text(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    markers = [
        "local model error:",
        "helyi modellhiba:",
        "local model is unavailable",
        "cannot answer right now because the local model is unavailable",
        "nem tudok most valaszolni, mert a helyi modell nem erheto el",
        "nem tudok most válaszolni, mert a helyi modell nem elérhető",
    ]
    return any(marker in lowered for marker in markers)


def _is_unsendable_reply_text(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    markers = [
        "i am {hatori}",
        "i am hatori",
        "verification ladder",
        "no memory changes",
        "connectivity state",
        "connectivity_state",
        "classify this as a daily task",
        "generated based on our previous conversation",
        "follow charter",
        "task prompt",
        "required behaviour",
    ]
    return any(marker in lowered for marker in markers)


def _normalize_lang_code(value: str | None) -> str:
    code = (value or "").strip().lower()
    if not code:
        return ""
    aliases = {
        "hungarian": "hu",
        "hu-hu": "hu",
        "english": "en",
        "en-us": "en",
        "en-gb": "en",
        "german": "de",
        "de-de": "de",
        "spanish": "es",
        "es-es": "es",
        "romanian": "ro",
        "ro-ro": "ro",
    }
    return aliases.get(code, code if code in {"hu", "en", "de", "es", "ro"} else "")


def _resolve_language_code(message: str, metadata: dict[str, Any], thread_context: list[dict[str, Any]]) -> str:
    hinted = _normalize_lang_code(
        (metadata or {}).get("language_hint")
        or (metadata or {}).get("identified_language")
        or (metadata or {}).get("language")
    )
    if hinted:
        return hinted

    auto_from_msg = ui.detect_message_language(message)
    if auto_from_msg != "en":
        return auto_from_msg

    # If current message is ambiguous/short, infer from recent thread context text.
    ctx_texts: list[str] = []
    for item in (thread_context or [])[-20:]:
        if not isinstance(item, dict):
            continue
        txt = (item.get("text") or "").strip()
        if txt:
            ctx_texts.append(txt)
    if ctx_texts:
        auto_from_ctx = ui.detect_message_language("\n".join(ctx_texts))
        if auto_from_ctx:
            return auto_from_ctx
    return auto_from_msg or "en"


def _generate_reply(
    message: str,
    conversation_id: str,
    user_id: str,
    *,
    language_override: str | None = None,
    thread_context: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], str, list[str], str]:
    language_code = _normalize_lang_code(language_override) or ui.detect_message_language(message)
    history_turns = ui.load_chat_history_for_prompt(chat_id=conversation_id, limit=10)
    ctx = thread_context or []
    for item in ctx[-10:]:
        if not isinstance(item, dict):
            continue
        txt = (item.get("text") or "").strip()
        role = (item.get("role") or "contact").strip().lower()
        if not txt:
            continue
        mapped_role = "assistant" if role == "me" else "user"
        history_turns.append({"role": mapped_role, "content": txt})
    history_turns = history_turns[-12:]
    pks_rows = ui.load_pks_context(limit=6)
    evidence_rows = ui.load_local_evidence_context(query=message, limit=5)
    source_lines = ui.build_human_sources_lines(language_code, pks_rows, evidence_rows)

    if ui.is_greeting_only(message, language_code):
        struct = ui.get_structured_reply(ui.greeting_clarifying_answer(language_code), language_code, message, sources=source_lines)
        return struct, language_code, source_lines, "greeting_shortcut"

    followup_answer = ui.resolve_followup_from_history(message, history_turns, language_code)
    if followup_answer:
        struct = ui.get_structured_reply(followup_answer, language_code, message, sources=source_lines)
        return struct, language_code, source_lines, "history_shortcut"

    is_planning = ui.is_daily_planning_request(message)
    model_task = "plan_write" if is_planning else "reply_write"
    model, adapter_error = ui.select_chat_model_adapter(task=model_task)
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
                plan_answer, assumptions, actions = ui.generate_planning_structured(
                    model=model,
                    language_code=language_code,
                    user_text=message,
                    context={
                        "history": [{"role": x.get("role", ""), "content": (x.get("content") or "")[:140]} for x in history_turns[-6:]],
                        "pks": ui.summarize_pks_for_model(pks_rows, limit=3),
                        "evidence": ui.summarize_evidence_for_model(evidence_rows, limit=3),
                    },
                )
            except Exception:
                # No hardcoded plan content: surface error and retry guidance only.
                plan_answer = (
                    "A helyi modell nem elérhető. Kérlek indítsd el az Ollama szolgáltatást, majd próbáld újra."
                    if language_code == "hu"
                    else "Local model is unavailable. Start Ollama and try again."
                )
                assumptions = ["Feltételezés: helyi modell jelenleg nem elérhető."] if language_code == "hu" else ["Assumption: local model is currently unavailable."]
                actions = ["P0 [ ] Indítsd el az Ollama szolgáltatást.", "P1 [ ] Küldd újra a napi tervezési kérést."] if language_code == "hu" else ["P0 [ ] Start Ollama service.", "P1 [ ] Resend the daily planning request."]

        rendered = ui.render_chat_default_output(
            plan_answer,
            language_code,
            message,
            sources=source_lines,
            assumptions_override=assumptions,
            next_actions_override=actions,
        )
        if ui._has_forbidden_user_visible_markers(rendered):
            rendered = ui.render_chat_default_output(
                "Rendszerhiba történt a válasz összeállításakor. Kérlek próbáld újra."
                if language_code == "hu"
                else "A system error occurred while assembling the response. Please retry.",
                language_code,
                message,
                sources=source_lines,
            )
            ui.insert_learning(
                kind="NegativeFeedback",
                confidence="High",
                details={
                    "vote": "down",
                    "category": "format",
                    "comment": "api planning rendered output failed validator",
                    "ui_context": {"route": "/v1/agent/respond", "source": "validator"},
                },
                related_interaction_id=user_id,
            )
        struct = ui.get_structured_reply(
            answer=plan_answer,
            language_code=language_code,
            user_text=message,
            sources=source_lines,
            assumptions_override=assumptions,
            next_actions_override=actions
        )
        return struct, language_code, source_lines, "planning_structured"

    system_prompt = ui.build_system_prompt()
    drafter_pack = ui.build_drafter_context_pack(message, language_code, history_turns, pks_rows, evidence_rows)
    task_prompt = ui.build_task_prompt(
        user_text=message,
        connectivity="OFFLINE",
        retrieved_context={
            "source": "reply.agent",
            "recent_history": [{"role": (x.get("role") or ""), "content": (x.get("content") or "")[:220]} for x in history_turns[-6:]],
            "pks_approved": ui.summarize_pks_for_model(pks_rows, limit=4),
            "local_evidence_top": ui.summarize_evidence_for_model(evidence_rows, limit=4),
            "drafter_pack": drafter_pack,
            "recent_feedback_summary": ui.summarize_recent_learning_for_model(limit=15),
        },
    )
    task_prompt += (
        "\nChat generation requirements:\n"
        f"- Respond in {ui.language_name(language_code)}.\n"
        "- Keep the answer factual and useful.\n"
        "- Do not repeat prompt/system instructions or the user message.\n"
        "- Answer directly; avoid awkward repetition of phrases.\n"
    )

    used_deterministic_fallback = False
    if adapter_error:
        raw_answer = _deterministic_reply_fallback(language_code, message)
        used_deterministic_fallback = True
    else:
        try:
            raw_answer = model.generate(system_prompt=system_prompt, task_prompt=task_prompt).strip()
        except Exception:
            raw_answer = _deterministic_reply_fallback(language_code, message)
            used_deterministic_fallback = True
    if not raw_answer:
        raw_answer = _deterministic_reply_fallback(language_code, message)
        used_deterministic_fallback = True
    if _is_model_unavailable_text(raw_answer):
        raw_answer = _deterministic_reply_fallback(language_code, message)
        used_deterministic_fallback = True
    if _is_unsendable_reply_text(raw_answer):
        raw_answer = _deterministic_reply_fallback(language_code, message)
        used_deterministic_fallback = True

    clean_answer, removed_ratio = ui._sanitize_with_stats(raw_answer)
    if model is not None and ui._needs_repair(raw_answer, clean_answer, removed_ratio):
        try:
            clean_answer = ui._repair_assistant_output(model, language_code, message, raw_answer)
        except Exception:
            clean_answer = _deterministic_reply_fallback(language_code, message)
            used_deterministic_fallback = True
    if model is not None and language_code == "hu" and not ui._looks_hungarian(clean_answer):
        try:
            clean_answer = ui._repair_assistant_output(model, language_code, message, clean_answer)
        except Exception:
            clean_answer = _deterministic_reply_fallback(language_code, message)
            used_deterministic_fallback = True

    clean_answer = ui.sanitize_assistant_output(clean_answer)
    if ui._has_forbidden_user_visible_markers(clean_answer) and model is not None:
        try:
            clean_answer = ui._repair_assistant_output_idsafe(model, language_code, message, clean_answer)
        except Exception:
            pass
    if ui._has_forbidden_user_visible_markers(clean_answer):
        clean_answer = _deterministic_reply_fallback(language_code, message)
        used_deterministic_fallback = True
        ui.insert_learning(
            kind="NegativeFeedback",
            confidence="High",
            details={
                "vote": "down",
                "category": "format",
                "comment": "api assistant output rejected by validator",
                "ui_context": {"route": "/v1/agent/respond", "source": "validator"},
            },
            related_interaction_id=user_id,
        )
    if not clean_answer:
        clean_answer = _deterministic_reply_fallback(language_code, message)
        used_deterministic_fallback = True
    if _is_model_unavailable_text(clean_answer):
        clean_answer = _deterministic_reply_fallback(language_code, message)
        used_deterministic_fallback = True
    if _is_unsendable_reply_text(clean_answer):
        clean_answer = _deterministic_reply_fallback(language_code, message)
        used_deterministic_fallback = True

    struct = ui.get_structured_reply(
        answer=clean_answer,
        language_code=language_code,
        user_text=message,
        sources=source_lines
    )
    generation_path = "standard_fallback" if used_deterministic_fallback else "standard"
    return struct, language_code, source_lines, generation_path


@app.get("/v1/health")
def health() -> dict[str, Any]:
    db = "ok"
    try:
        ui.psql("SELECT 1;")
    except Exception:
        db = "fail"
    model, model_name = _model_status()
    runtime_status = _runtime_status()
    task_model_routing = _task_routing_status()
    return {
        "ok": True,
        "statusMessage": "online",
        "status": "ok",
        "version": VERSION_FILE.read_text(encoding="utf-8").strip(),
        "ui_port": int((os.environ.get("UI_PORT") or "23571").strip()),
        "api_port": int((os.environ.get("API_PORT") or "23572").strip()),
        "db": db,
        "model": model,
        "model_name": model_name,
        "runtime_status": runtime_status,
        "task_model_routing": task_model_routing,
        "request_counts_last_minute": _RATE_LIMITER.counts_last_minute(),
    }


@app.post("/v1/agent/respond")
def agent_respond(body: RespondBody, x_hatori_token: str | None = Header(default=None, alias="X-Hatori-Token")) -> dict[str, Any]:
    token = _require_token_value(x_hatori_token)
    _enforce_rate("respond", token)
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    conversation_id = _conversation_id(body.conversation_id)
    external_request_id = (body.external_request_id or (body.metadata or {}).get("external_request_id") or "").strip()
    if external_request_id:
        existing_rows = ui.psql_json(
            "SELECT id, COALESCE(metadata->>'related_user_interaction_id','') AS related_id, content, "
            "COALESCE(metadata->>'language','') AS language "
            "FROM interaction_events "
            "WHERE role='assistant' "
            "AND COALESCE(metadata->>'source','')='reply' "
            f"AND COALESCE(metadata->>'external_request_id','')='{ui._esc_sql(external_request_id)}' "
            "ORDER BY occurred_at DESC LIMIT 1;"
        )
        if existing_rows:
            row = existing_rows[0]
            language = (row.get("language") or "").strip() or ui.detect_message_language(message)
            source_lines = ui.build_human_sources_lines(
                language,
                ui.load_pks_context(limit=6),
                ui.load_local_evidence_context(query=message, limit=5),
            )
            return {
                "conversation_id": conversation_id,
                "message_id": body.message_id,
                "user_interaction_id": row.get("related_id", ""),
                "assistant_interaction_id": row.get("id", ""),
                "assistant_message": row.get("content", ""),
                "language": language,
                "connectivity_state": "OFFLINE",
                "sources": source_lines,
            }

    language_code = _resolve_language_code(message, body.metadata or {}, body.thread_context or [])
    meta = {
        "source": "reply",
        "chat_id": conversation_id,
        "conversation_id": conversation_id,
        "message_id": body.message_id,
        "sender_id": body.sender_id,
        "received_at": body.received_at,
        "mode": body.mode or "chat",
        "platform": (body.metadata or {}).get("platform", ""),
        "channel": (body.metadata or {}).get("channel", ""),
        "external_request_id": external_request_id,
        "identified_language": language_code,
        "thread_context_count": len(body.thread_context or []),
        "extra": (body.metadata or {}).get("extra", {}),
    }
    user_id = ui.insert_interaction("user", message, meta)
    assistant_struct, language_code, source_lines, gen_path = _generate_reply(
        message,
        conversation_id,
        user_id,
        language_override=language_code,
        thread_context=body.thread_context or [],
    )
    model_adapter, _adapter_err = ui.select_chat_model_adapter(task="plan_write" if ui.is_daily_planning_request(message) else "reply_write")
    assistant_interaction_id = ui.insert_interaction(
        "assistant",
        assistant_struct["answer"],
        {
            "source": "reply",
            "chat_id": conversation_id,
            "conversation_id": conversation_id,
            "message_id": body.message_id,
            "sender_id": body.sender_id,
            "model_adapter": model_adapter.name if model_adapter is not None else "unavailable",
            "generation_path": gen_path,
            "language": language_code,
            "external_request_id": external_request_id,
            "related_user_interaction_id": user_id,
        },
    )
    return {
        "conversation_id": conversation_id,
        "message_id": body.message_id,
        "user_interaction_id": user_id,
        "assistant_interaction_id": assistant_interaction_id,
        "assistant_message": assistant_struct["answer"],
        "next_actions": assistant_struct["next_actions"],
        "assumptions": assistant_struct["assumptions"],
        "language": language_code,
        "connectivity_state": assistant_struct["connectivity_state"],
        "sources": source_lines,
    }


@app.post("/v1/agent/feedback")
def agent_feedback(body: FeedbackBody, x_hatori_token: str | None = Header(default=None, alias="X-Hatori-Token")) -> dict[str, str]:
    require_token(x_hatori_token)
    if not ui.UUID_RE.match(body.assistant_interaction_id):
        raise HTTPException(status_code=400, detail="invalid assistant_interaction_id")
    role = ui.psql(
        "SELECT role FROM interaction_events "
        f"WHERE id='{ui._esc_sql(body.assistant_interaction_id)}' LIMIT 1;"
    ).strip()
    if role != "assistant":
        raise HTTPException(status_code=400, detail="assistant_interaction_id must reference assistant row")

    vote = body.vote.strip().lower()
    if vote not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="vote must be up or down")
    external_request_id = (body.external_request_id or "").strip()
    if external_request_id:
        existing = ui.psql(
            "SELECT id FROM learning_events "
            f"WHERE related_interaction_id='{ui._esc_sql(body.assistant_interaction_id)}' "
            f"AND COALESCE(details->>'external_request_id','')='{ui._esc_sql(external_request_id)}' "
            "ORDER BY occurred_at DESC LIMIT 1;"
        ).strip()
        if existing:
            return {"learning_event_id": existing}
    kind = "PositiveFeedback" if vote == "up" else "NegativeFeedback"
    confidence = "High" if vote == "up" else "Medium"
    lid = ui.insert_learning(
        kind=kind,
        confidence=confidence,
        details={
            "vote": vote,
            "category": body.category.strip() or "Other",
            "comment": body.comment.strip(),
            "external_request_id": external_request_id,
            "ui_context": {"route": "/v1/agent/feedback", "source": "reply"},
        },
        related_interaction_id=body.assistant_interaction_id,
    )
    return {"learning_event_id": lid}


@app.post("/v1/agent/outcome")
def agent_outcome(body: OutcomeBody, x_hatori_token: str | None = Header(default=None, alias="X-Hatori-Token")) -> dict[str, Any]:
    token = _require_token_value(x_hatori_token)
    _enforce_rate("outcome", token)
    external_outcome_id = (body.external_outcome_id or "").strip()
    if not external_outcome_id:
        raise HTTPException(status_code=400, detail="external_outcome_id is required")
    if not ui.UUID_RE.match(body.assistant_interaction_id):
        raise HTTPException(status_code=400, detail="invalid assistant_interaction_id")
    role = ui.psql(
        "SELECT role FROM interaction_events "
        f"WHERE id='{ui._esc_sql(body.assistant_interaction_id)}' LIMIT 1;"
    ).strip()
    if role != "assistant":
        raise HTTPException(status_code=400, detail="assistant_interaction_id must reference assistant row")

    existing_delivery_id = _delivery_event_id_by_external_outcome_id(external_outcome_id)
    if existing_delivery_id:
        existing_learning = ui.psql(
            "SELECT id FROM learning_events "
            f"WHERE COALESCE(details->>'external_outcome_id','')='{ui._esc_sql(external_outcome_id)}' "
            "ORDER BY occurred_at DESC LIMIT 1;"
        ).strip()
        return {
            "delivery_event_id": existing_delivery_id,
            "learning_event_id": existing_learning,
            "duplicate": True,
        }

    existing = ui.psql(
        "SELECT id FROM learning_events "
        f"WHERE COALESCE(details->>'external_outcome_id','')='{ui._esc_sql(external_outcome_id)}' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    ).strip()
    if existing:
        return {"learning_event_id": existing, "duplicate": True}

    status = (body.status or "").strip().lower()
    if status not in {"sent_as_is", "edited_then_sent", "not_sent"}:
        raise HTTPException(status_code=400, detail="status must be sent_as_is|edited_then_sent|not_sent")
    original_text = (body.original_text or "").strip()
    final_sent_text = (body.final_sent_text or "").strip()
    diff_text = (body.diff or "").strip()
    if status == "edited_then_sent":
        if not original_text:
            raise HTTPException(status_code=400, detail="original_text is required when status=edited_then_sent")
        if not final_sent_text:
            raise HTTPException(status_code=400, detail="final_sent_text is required when status=edited_then_sent")

    if status == "sent_as_is":
        kind = "PositiveFeedback"
        confidence = "High"
    elif status == "edited_then_sent":
        kind = "NegativeFeedback"
        confidence = "High"
    else:
        kind = "Neutral"
        confidence = "Low"

    details = {
        "status": status,
        "external_outcome_id": external_outcome_id,
        "platform": (body.platform or "other").strip() or "other",
        "conversation_id": (body.conversation_id or "").strip(),
        "recipient_id": (body.recipient_id or "").strip(),
        "original_text": original_text,
        "edit_reason": (body.edit_reason or "").strip(),
        "final_sent_text": final_sent_text,
        "diff": diff_text,
        "metadata": body.metadata or {},
        "ui_context": {"route": "/v1/agent/outcome", "source": "reply"},
    }
    delivery_id = str(uuid.uuid4())
    ui.psql(
        "INSERT INTO delivery_events "
        "(id, external_outcome_id, assistant_interaction_id, status, platform, recipient_id, conversation_id, "
        "original_text, final_sent_text, diff, edit_reason, metadata) "
        f"VALUES ('{delivery_id}', '{ui._esc_sql(external_outcome_id)}', '{ui._esc_sql(body.assistant_interaction_id)}', "
        f"'{ui._esc_sql(status)}', '{ui._esc_sql(details['platform'])}', '{ui._esc_sql(details['recipient_id'])}', "
        f"'{ui._esc_sql(details['conversation_id'])}', '{ui._esc_sql(original_text)}', '{ui._esc_sql(final_sent_text)}', "
        f"'{ui._esc_sql(diff_text)}', '{ui._esc_sql(details['edit_reason'])}', "
        f"'{ui._esc_sql(json.dumps(body.metadata or {}, ensure_ascii=False))}'::jsonb);"
    )
    lid = ui.insert_learning(
        kind=kind,
        confidence=confidence,
        details=details,
        related_interaction_id=body.assistant_interaction_id,
    )
    return {"delivery_event_id": delivery_id, "learning_event_id": lid, "duplicate": False}


@app.post("/v1/ingest/event")
def ingest_event(body: IngestBody, x_hatori_token: str | None = Header(default=None, alias="X-Hatori-Token")) -> dict[str, Any]:
    token = _require_token_value(x_hatori_token)
    _enforce_rate("ingest", token)
    event_id = (body.external_event_id or body.event_id or "").strip()
    if not event_id:
        raise HTTPException(status_code=400, detail="external_event_id is required")
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required for /v1/ingest/event")

    existing = _interaction_id_by_external_event_id(event_id, "reply.ingest_event")
    if existing:
        existing_artefact = _artifact_id_by_external_event_id(event_id, "reply.ingest_event")
        return {"stored": True, "interaction_id": existing, "artefact_id": existing_artefact or None, "duplicate": True}

    conversation_id = _conversation_id(body.conversation_id)
    role = "user" if body.kind in {"email", "imessage"} else "system"
    content_size = len(content.encode("utf-8"))
    if content_size > 200 * 1024:
        raise HTTPException(status_code=413, detail="content too large for /v1/ingest/event; use /v1/artefacts/upload")
    interaction_id = ui.insert_interaction(
        role,
        content,
        {
            "source": "reply.ingest_event",
            "external_event_id": event_id,
            "kind": body.kind,
            "chat_id": conversation_id,
            "conversation_id": conversation_id,
            "sender_id": body.sender_id or "",
            "metadata": body.metadata or {},
        },
    )
    return {"stored": True, "interaction_id": interaction_id, "artefact_id": None, "duplicate": False}


@app.post("/v1/artefacts/upload")
async def artefacts_upload(
    external_event_id: str = Form(...),
    kind: str = Form(...),
    file: UploadFile = File(...),
    conversation_id: str = Form(default=""),
    sender_id: str = Form(default=""),
    metadata: str = Form(default=""),
    x_hatori_token: str | None = Header(default=None, alias="X-Hatori-Token"),
) -> dict[str, Any]:
    require_token(x_hatori_token)
    event_id = external_event_id.strip()
    if not event_id:
        raise HTTPException(status_code=400, detail="external_event_id is required")
    existing = _artifact_id_by_external_event_id(event_id, "reply.upload")
    if existing:
        chunks_created = int(
            ui.psql(f"SELECT count(*) FROM embeddings WHERE artefact_id='{ui._esc_sql(existing)}';").strip() or "0"
        )
        sha = ui.psql(f"SELECT COALESCE(sha256,'') FROM artefacts WHERE id='{ui._esc_sql(existing)}' LIMIT 1;").strip()
        return {"artefact_id": existing, "sha256": sha, "chunks_created": chunks_created}

    meta_obj = _parse_metadata_json(metadata)
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="file must not be empty")
    UPLOADS_API_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    safe_name = Path(file.filename or "upload.bin").name
    dest = UPLOADS_API_DIR / f"{ts}__{safe_name}"
    dest.write_bytes(raw_bytes)
    media_type = (file.content_type or "").strip() or _detect_media_type(dest)
    artefact_id, sha, chunks_created = _ingest_file_to_artefact(
        source="reply.upload",
        external_event_id=event_id,
        kind=kind.strip() or "other",
        file_path=dest,
        media_type=media_type,
        provided_sha256=None,
        conversation_id=(conversation_id or "").strip() or None,
        sender_id=(sender_id or "").strip() or None,
        metadata=meta_obj,
    )
    return {"artefact_id": artefact_id, "sha256": sha, "chunks_created": chunks_created}


@app.post("/v1/artefacts/ingest_path")
def artefacts_ingest_path(
    body: IngestPathBody,
    x_hatori_token: str | None = Header(default=None, alias="X-Hatori-Token"),
) -> dict[str, Any]:
    require_token(x_hatori_token)
    if (os.environ.get("HATORI_ALLOW_PATH_INGEST") or "0").strip() != "1":
        raise HTTPException(status_code=403, detail="path ingest disabled")
    event_id = body.external_event_id.strip()
    if not event_id:
        raise HTTPException(status_code=400, detail="external_event_id is required")
    existing = _artifact_id_by_external_event_id(event_id, "reply.path")
    if existing:
        chunks_created = int(
            ui.psql(f"SELECT count(*) FROM embeddings WHERE artefact_id='{ui._esc_sql(existing)}';").strip() or "0"
        )
        sha = ui.psql(f"SELECT COALESCE(sha256,'') FROM artefacts WHERE id='{ui._esc_sql(existing)}' LIMIT 1;").strip()
        return {"artefact_id": existing, "sha256": sha, "chunks_created": chunks_created}

    path = Path(body.path).expanduser()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=400, detail="path does not exist or is not a file")
    if not _path_allowed(path):
        raise HTTPException(status_code=403, detail="path is outside allowlist")
    media_type = _detect_media_type(path)
    artefact_id, sha, chunks_created = _ingest_file_to_artefact(
        source="reply.path",
        external_event_id=event_id,
        kind=body.kind.strip() or "other",
        file_path=path,
        media_type=media_type,
        provided_sha256=body.sha256,
        conversation_id=(body.metadata or {}).get("conversation_id"),
        sender_id=(body.metadata or {}).get("sender_id"),
        metadata=body.metadata or {},
    )
    return {"artefact_id": artefact_id, "sha256": sha, "chunks_created": chunks_created}


@app.get("/v1/search")
def search(
    q: str,
    k: int = 5,
    conversation_id: str | None = None,
    x_hatori_token: str | None = Header(default=None, alias="X-Hatori-Token"),
) -> list[dict[str, Any]]:
    require_token(x_hatori_token)
    if not q.strip():
        return []
    payload = ui.search_runtime(query=q, limit=max(1, min(20, int(k))), allow_pending=False)
    out: list[dict[str, Any]] = []
    for row in payload.get("results", []):
        uri = (row.get("artefact_uri") or "").strip()
        title = os.path.basename(uri) if uri else (row.get("provenance") or "LocalDoc")
        source = "PKS Approved" if str(row.get("citation", "")).startswith("pks:") else "LocalDoc"
        out.append(
            {
                "snippet": (row.get("excerpt") or "")[:240],
                "source": source,
                "title": title,
                "path": ui._short_path(uri),
                "score": row.get("score"),
            }
        )
    return out
