import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi import Header
from fastapi import HTTPException
from pydantic import BaseModel
from pydantic import Field

from hatori.embeddings import get_embeddings_adapter
import ui.app as ui

ROOT_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT_DIR / "VERSION"
app = FastAPI(title="Hatori API", version=VERSION_FILE.read_text(encoding="utf-8").strip())


def require_token(x_hatori_token: str | None = Header(default=None, alias="X-Hatori-Token")) -> None:
    expected = (os.environ.get("HATORI_API_TOKEN") or "").strip()
    if not expected or x_hatori_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


def _model_status() -> tuple[str, str]:
    explicit = (os.environ.get("HATORI_MODEL") or "").strip().lower()
    if explicit:
        if explicit == "ollama":
            return "ollama", (os.environ.get("HATORI_OLLAMA_MODEL") or "llama3.2:3b").strip()
        return explicit, ""
    if ui.prefer_ollama_if_available():
        return "ollama", (os.environ.get("HATORI_OLLAMA_MODEL") or "llama3.2:3b").strip()
    return "none", ""


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
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackBody(BaseModel):
    assistant_interaction_id: str
    vote: str
    category: str = "Other"
    comment: str = ""
    external_request_id: str | None = None


class IngestBody(BaseModel):
    event_id: str
    kind: str
    conversation_id: str | None = None
    sender_id: str | None = None
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def _generate_reply(message: str, conversation_id: str, user_id: str) -> tuple[str, str, list[str], str]:
    language_code = ui.detect_message_language(message)
    history_turns = ui.load_chat_history_for_prompt(chat_id=conversation_id, limit=10)
    pks_rows = ui.load_pks_context(limit=6)
    evidence_rows = ui.load_local_evidence_context(query=message, limit=5)
    source_lines = ui.build_human_sources_lines(language_code, pks_rows, evidence_rows)

    if ui.is_greeting_only(message, language_code):
        answer = ui.render_chat_default_output(ui.greeting_clarifying_answer(language_code), language_code, message, sources=source_lines)
        return answer, language_code, source_lines, "greeting_shortcut"

    followup_answer = ui.resolve_followup_from_history(message, history_turns, language_code)
    if followup_answer:
        answer = ui.render_chat_default_output(followup_answer, language_code, message, sources=source_lines)
        return answer, language_code, source_lines, "history_shortcut"

    model, adapter_error = ui.select_chat_model_adapter()
    if ui.is_daily_planning_request(message):
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
        return rendered, language_code, source_lines, "planning_structured"

    system_prompt = ui.build_system_prompt()
    task_prompt = ui.build_task_prompt(
        user_text=message,
        connectivity="OFFLINE",
        retrieved_context={
            "source": "reply.agent",
            "recent_history": [{"role": (x.get("role") or ""), "content": (x.get("content") or "")[:220]} for x in history_turns[-6:]],
            "pks_approved": ui.summarize_pks_for_model(pks_rows, limit=4),
            "local_evidence_top": ui.summarize_evidence_for_model(evidence_rows, limit=4),
        },
    )
    task_prompt += (
        "\nChat generation requirements:\n"
        f"- Respond in {ui.language_name(language_code)}.\n"
        "- Keep the answer factual and useful.\n"
        "- Do not repeat prompt/system instructions.\n"
        "- Answer directly.\n"
    )

    if adapter_error:
        raw_answer = ui.localized_model_error(language_code, adapter_error)
    else:
        try:
            raw_answer = model.generate(system_prompt=system_prompt, task_prompt=task_prompt).strip()
        except Exception as exc:
            raw_answer = ui.localized_model_error(language_code, str(exc))
    if not raw_answer:
        raw_answer = ui.localized_model_error(language_code, "empty response")

    clean_answer, removed_ratio = ui._sanitize_with_stats(raw_answer)
    if model is not None and ui._needs_repair(raw_answer, clean_answer, removed_ratio):
        try:
            clean_answer = ui._repair_assistant_output(model, language_code, message, raw_answer)
        except Exception:
            clean_answer = ui.localized_model_error(language_code, "unsafe model output removed")
    if model is not None and language_code == "hu" and not ui._looks_hungarian(clean_answer):
        try:
            clean_answer = ui._repair_assistant_output(model, language_code, message, clean_answer)
        except Exception:
            clean_answer = "Rendszerhiba történt a válasz összeállításakor. Kérlek próbáld újra."

    clean_answer = ui.sanitize_assistant_output(clean_answer)
    if ui._has_forbidden_user_visible_markers(clean_answer) and model is not None:
        try:
            clean_answer = ui._repair_assistant_output_idsafe(model, language_code, message, clean_answer)
        except Exception:
            pass
    if ui._has_forbidden_user_visible_markers(clean_answer):
        clean_answer = (
            "Rendszerhiba történt a válasz összeállításakor. Kérlek próbáld újra."
            if language_code == "hu"
            else "A system error occurred while assembling the response. Please retry."
        )
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
        clean_answer = ui.localized_model_error(language_code, "empty sanitized output")

    rendered = ui.render_chat_default_output(clean_answer, language_code, message, sources=source_lines)
    return rendered, language_code, source_lines, "standard"


@app.get("/v1/health")
def health() -> dict[str, Any]:
    db = "ok"
    try:
        ui.psql("SELECT 1;")
    except Exception:
        db = "fail"
    model, model_name = _model_status()
    return {
        "status": "ok",
        "version": VERSION_FILE.read_text(encoding="utf-8").strip(),
        "ui_port": 8093,
        "api_port": 8094,
        "db": db,
        "model": model,
        "model_name": model_name,
    }


@app.post("/v1/agent/respond")
def agent_respond(body: RespondBody, x_hatori_token: str | None = Header(default=None, alias="X-Hatori-Token")) -> dict[str, Any]:
    require_token(x_hatori_token)
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    conversation_id = _conversation_id(body.conversation_id)

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
        "extra": (body.metadata or {}).get("extra", {}),
    }
    user_id = ui.insert_interaction("user", message, meta)
    assistant_message, language_code, source_lines, gen_path = _generate_reply(message, conversation_id, user_id)
    model_adapter, _adapter_err = ui.select_chat_model_adapter()
    assistant_id = ui.insert_interaction(
        "assistant",
        assistant_message,
        {
            "source": "reply",
            "chat_id": conversation_id,
            "conversation_id": conversation_id,
            "message_id": body.message_id,
            "sender_id": body.sender_id,
            "model_adapter": model_adapter.name if model_adapter is not None else "unavailable",
            "generation_path": gen_path,
            "language": language_code,
            "related_user_interaction_id": user_id,
        },
    )
    return {
        "conversation_id": conversation_id,
        "user_interaction_id": user_id,
        "assistant_interaction_id": assistant_id,
        "assistant_message": assistant_message,
        "language": language_code,
        "connectivity_state": "OFFLINE",
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
    kind = "PositiveFeedback" if vote == "up" else "NegativeFeedback"
    confidence = "High" if vote == "up" else "Medium"
    lid = ui.insert_learning(
        kind=kind,
        confidence=confidence,
        details={
            "vote": vote,
            "category": body.category.strip() or "Other",
            "comment": body.comment.strip(),
            "external_request_id": body.external_request_id or "",
            "ui_context": {"route": "/v1/agent/feedback", "source": "reply"},
        },
        related_interaction_id=body.assistant_interaction_id,
    )
    return {"learning_event_id": lid}


@app.post("/v1/ingest/event")
def ingest_event(body: IngestBody, x_hatori_token: str | None = Header(default=None, alias="X-Hatori-Token")) -> dict[str, Any]:
    require_token(x_hatori_token)
    event_id = body.event_id.strip()
    if not event_id:
        raise HTTPException(status_code=400, detail="event_id is required")

    existing = ui.psql(
        "SELECT id FROM interaction_events "
        f"WHERE COALESCE(metadata->>'event_id','')='{ui._esc_sql(event_id)}' "
        "AND COALESCE(metadata->>'source','')='reply' "
        "ORDER BY occurred_at DESC LIMIT 1;"
    ).strip()
    if existing:
        return {"stored": True, "interaction_id": existing, "artefact_id": None}

    conversation_id = _conversation_id(body.conversation_id)
    role = "user" if body.kind in {"email", "imessage"} else "system"
    interaction_id = ui.insert_interaction(
        role,
        body.content,
        {
            "source": "reply",
            "event_id": event_id,
            "kind": body.kind,
            "chat_id": conversation_id,
            "conversation_id": conversation_id,
            "sender_id": body.sender_id or "",
            "metadata": body.metadata or {},
        },
    )

    artefact_id = None
    if len(body.content) >= 1200:
        artefact_id = str(uuid.uuid4())
        title = f"{body.kind}-{event_id}"
        meta = {
            "source": "reply.ingest",
            "event_id": event_id,
            "kind": body.kind,
            "sensitivity": "Private",
            "provenance": "LocalDoc",
        }
        uri = f"reply://{event_id}"
        sha = ui.hashlib.sha256(body.content.encode("utf-8")).hexdigest()
        ui.psql(
            "INSERT INTO artefacts (id, kind, uri, title, media_type, sha256, metadata) "
            f"VALUES ('{artefact_id}', 'note', '{ui._esc_sql(uri)}', '{ui._esc_sql(title)}', "
            f"'text/plain', '{sha}', '{ui._esc_sql(json.dumps(meta, ensure_ascii=False))}'::jsonb);"
        )
        chunks = ui.chunk_text(body.content)
        adapter = get_embeddings_adapter()
        vectors = adapter.embed(chunks) if chunks else []
        for idx, chunk in enumerate(chunks):
            emb_id = str(uuid.uuid4())
            chunk_id = f"{artefact_id}:{idx}"
            emb_sql = ui._esc_sql(ui.vector_sql_literal(vectors[idx]))
            cmeta = {
                "source": "reply.ingest",
                "event_id": event_id,
                "index": idx,
                "embedder": adapter.name,
                "embed_dim": adapter.dimension,
            }
            ui.psql(
                "INSERT INTO embeddings (id, artefact_id, chunk_id, content, embedding, metadata) "
                f"VALUES ('{emb_id}', '{artefact_id}', '{ui._esc_sql(chunk_id)}', '{ui._esc_sql(chunk)}', "
                f"'{emb_sql}'::vector, '{ui._esc_sql(json.dumps(cmeta, ensure_ascii=False))}'::jsonb);"
            )

    return {"stored": True, "interaction_id": interaction_id, "artefact_id": artefact_id}


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
