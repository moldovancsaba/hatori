import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHARTER_PATH = ROOT / "docs" / "01-charters" / "hatori-charter-v3.md"
RUNTIME_SYSTEM_PATH = ROOT / "docs" / "09-prompts" / "runtime-system-min.md"
TASK_TEMPLATE_PATH = ROOT / "docs" / "09-prompts" / "task-prompt-template.md"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_fences(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("```"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def build_system_prompt() -> str:
    charter = _strip_fences(_read_text(CHARTER_PATH))
    runtime = _strip_fences(_read_text(RUNTIME_SYSTEM_PATH))
    return (
        "Canonical sources:\n"
        f"- {CHARTER_PATH.as_posix()}\n"
        f"- {RUNTIME_SYSTEM_PATH.as_posix()}\n\n"
        "Never output task prompt, retrieved context dumps, or tool scaffolding.\n\n"
        f"{runtime}\n\n{charter}"
    )


def build_task_prompt(user_text: str, connectivity: str, retrieved_context: dict, system_hints: list[str] | None = None) -> str:
    template = _strip_fences(_read_text(TASK_TEMPLATE_PATH))
    context_json = json.dumps(retrieved_context, ensure_ascii=False, indent=2)
    hints_text = ""
    if system_hints:
        hints_text = "System hints for this request:\n" + "\n".join(f"- {h}" for h in system_hints) + "\n\n"
    
    return (
        f"Canonical task template source: {TASK_TEMPLATE_PATH.as_posix()}\n\n"
        f"{template}\n\n"
        f"Connectivity: {connectivity}\n"
        f"{hints_text}"
        f"User request:\n{user_text}\n\n"
        f"Retrieved context (JSON):\n{context_json}\n"
    )


def render_default_output(payload: dict) -> str:
    evidence_lines: list[str]
    if payload.get("evidence"):
        evidence_lines = [
            f"- [{e['citation']}] {e['title']} | score={e['score']} | excerpt={e['excerpt']}"
            for e in payload["evidence"]
        ]
    else:
        evidence_lines = ["- No local evidence found."]

    actions = "\n".join(f"- {x}" for x in payload.get("next_actions", []))
    assumptions = "\n".join(f"- {x}" for x in payload.get("assumptions", []))
    evidence = "\n".join(evidence_lines)
    memory_patch = payload.get("memory_patch", "No memory changes.")
    learning_log = payload.get("learning_log", "No learning event recorded.")

    return (
        f"1) Connectivity State: {payload['connectivity_state']}\n"
        f"2) Answer / Recommendation\n{payload['answer']}\n\n"
        f"3) Evidence & Sources\n{evidence}\n\n"
        f"4) Assumptions & Uncertainties\n{assumptions}\n\n"
        f"5) Next Actions\n{actions}\n\n"
        f"6) Memory Patch\n{memory_patch}\n\n"
        f"7) Learning Log (J)\n{learning_log}"
    )
