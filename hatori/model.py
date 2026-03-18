import hashlib
import os
from pathlib import Path
import subprocess
from typing import Protocol
import shutil
import json
import urllib.request
import urllib.error
import urllib.parse


class ModelAdapter(Protocol):
    name: str

    def generate(self, system_prompt: str, task_prompt: str) -> str:
        ...

    def healthcheck(self) -> dict:
        ...


class NullAdapter:
    name = "none"

    def _lang_from_task_prompt(self, task_prompt: str) -> str:
        lowered = task_prompt.lower()
        if "respond in hungarian" in lowered:
            return "hu"
        if "respond in romanian" in lowered:
            return "ro"
        if "respond in spanish" in lowered:
            return "es"
        if "respond in french" in lowered:
            return "fr"
        if "respond in german" in lowered:
            return "de"
        return "en"

    def generate(self, system_prompt: str, task_prompt: str) -> str:
        if "LEAKAGE_FIXTURE" in task_prompt:
            return (
                "TASK PROMPT (Hatori)\n"
                "Retrieved PKS: none\n"
                "Required behaviour: output template\n"
                "```text\nConnectivity: OFFLINE\nTime: now\n```\n"
                "Final: please clean me"
            )
        if "UUID_LEAK_FIXTURE" in task_prompt:
            return (
                "User request: UUID_LEAK_FIXTURE\n"
                "State assumptions and cite provenance.\n"
                "retrieved pks: 123e4567-e89b-12d3-a456-426614174000\n"
                "emb:artefact-1:chunk-2\n"
            )
        # Deterministic planning JSON for golden tests (HATORI_MODEL=none).
        if '"answer_body"' in task_prompt and '"next_actions"' in task_prompt and "Respond in Hungarian" in task_prompt:
            return json.dumps(
                {
                    "answer_body": "Rövid mai napi terv (determinisztikus). Pragmatikus feladatok és következő lépések.",
                    "assumptions": [
                        "Nincs átadott naptár; naptár adat hiányzik.",
                        "Nincs megadott meeting; meetingek nincsenek beállítva.",
                    ],
                    "next_actions": [
                        "P0 [ ] Egyetlen legfontosabb kimenetel ma.",
                        "P1 [ ] Első konkrét mai feladat.",
                        "P1 [ ] Második mai feladat.",
                        "P1 [ ] Harmadik mai teendő.",
                        "P1 [ ] Negyedik lépés.",
                        "P2 [ ] Nap zárása, összefoglaló.",
                    ],
                },
                ensure_ascii=False,
            )
        digest = hashlib.sha256((system_prompt + "\n" + task_prompt).encode("utf-8")).hexdigest()[:12]
        lang = self._lang_from_task_prompt(task_prompt)
        if lang == "hu":
            return (
                "Offline determinisztikus valasz (NullAdapter). "
                f"Keresi ujjlenyomat: {digest}. "
                "Ma pragmatikus feladat lista javasolt; kritikus feltetelezeseket jelolok, majd kovetkezo lepesek checklistat adok."
            )
        if lang == "ro":
            return (
                "Raspuns offline determinist (NullAdapter). "
                f"Amprenta cererii: {digest}. "
                "Recomandare: foloseste o lista zilnica in 5 puncte si ajusteaza dupa capacitatea reala."
            )
        if lang == "es":
            return (
                "Respuesta offline determinista (NullAdapter). "
                f"Huella de solicitud: {digest}. "
                "Recomendacion: usa una lista diaria de 5 puntos y ajustala a tu capacidad real."
            )
        if lang == "fr":
            return (
                "Reponse hors ligne deterministe (NullAdapter). "
                f"Empreinte de requete: {digest}. "
                "Recommendation: utilisez une checklist quotidienne en 5 points et ajustez-la a votre capacite reelle."
            )
        if lang == "de":
            return (
                "Deterministische Offline-Antwort (NullAdapter). "
                f"Anfrage-Fingerabdruck: {digest}. "
                "Empfehlung: nutze eine taegliche 5-Punkte-Checkliste und passe sie an deine reale Kapazitaet an."
            )
        return (
            "Offline deterministic response (NullAdapter). "
            f"Request fingerprint: {digest}. "
            "Recommendation: use a concise 5-point daily checklist and adapt it to real capacity."
        )

    def healthcheck(self) -> dict:
        return {"ok": True, "adapter": self.name, "offline": True}


class LlamaCppAdapter:
    name = "llamacpp"

    def __init__(self) -> None:
        self.model_path = (
            os.environ.get("HATORI_LLAMA_MODEL")
            or os.environ.get("HATORI_LLAMACPP_MODEL_PATH")
            or ""
        ).strip()
        self.binary = (
            os.environ.get("HATORI_LLAMA_BIN")
            or os.environ.get("HATORI_LLAMACPP_BIN")
            or "llama-cli"
        ).strip()
        self.max_tokens = int(
            (
                os.environ.get("HATORI_LLAMA_MAX_TOKENS")
                or os.environ.get("HATORI_LLAMACPP_MAX_TOKENS")
                or "256"
            ).strip()
        )
        self.ctx = int((os.environ.get("HATORI_LLAMA_CTX") or "4096").strip())
        self.threads = int((os.environ.get("HATORI_LLAMA_THREADS") or "4").strip())

    def _validate(self) -> None:
        if not self.model_path:
            raise RuntimeError("HATORI_LLAMA_MODEL is required for HATORI_MODEL=llamacpp")
        if not Path(self.model_path).exists():
            raise RuntimeError(f"Llama model file not found: {self.model_path}")
        if not shutil.which(self.binary):
            raise RuntimeError(f"llama.cpp binary not found in PATH: {self.binary}")
        if self.ctx <= 0:
            raise RuntimeError("HATORI_LLAMA_CTX must be a positive integer")
        if self.threads <= 0:
            raise RuntimeError("HATORI_LLAMA_THREADS must be a positive integer")
        if self.max_tokens <= 0:
            raise RuntimeError("HATORI_LLAMA_MAX_TOKENS must be a positive integer")

    def generate(self, system_prompt: str, task_prompt: str) -> str:
        self._validate()
        prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{task_prompt}\n<|assistant|>\n"
        cmd = [
            self.binary,
            "-m",
            self.model_path,
            "-c",
            str(self.ctx),
            "-t",
            str(self.threads),
            "-n",
            str(self.max_tokens),
            "-p",
            prompt,
            "--no-display-prompt",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip() or "llama.cpp generation failed"
            raise RuntimeError(err)
        return proc.stdout.strip()

    def healthcheck(self) -> dict:
        try:
            self._validate()
            return {
                "ok": True,
                "adapter": self.name,
                "binary": self.binary,
                "model_path": self.model_path,
                "ctx": self.ctx,
                "threads": self.threads,
                "max_tokens": self.max_tokens,
                "offline": True,
            }
        except Exception as exc:
            return {"ok": False, "adapter": self.name, "error": str(exc), "offline": True}


class OllamaAdapter:
    name = "ollama"

    def __init__(self, model: str | None = None, base_url: str | None = None, timeout: int | None = None) -> None:
        self.base_url = (base_url or os.environ.get("HATORI_OLLAMA_URL") or "http://127.0.0.1:11434").strip().rstrip("/")
        self.model = (model or os.environ.get("HATORI_OLLAMA_MODEL") or "llama3.2:3b").strip()
        self.timeout = int((str(timeout) if timeout is not None else (os.environ.get("HATORI_OLLAMA_TIMEOUT") or "60")).strip())

    def _request_json(self, path: str, payload: dict | None = None) -> dict:
        data = None
        headers = {"Accept": "application/json"}
        method = "GET"
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            method = "POST"
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body) if body else {}

    def _validate(self) -> None:
        if not self.model:
            raise RuntimeError("HATORI_OLLAMA_MODEL must be set")
        if not (self.base_url.startswith("http://127.0.0.1") or self.base_url.startswith("http://localhost")):
            raise RuntimeError("HATORI_OLLAMA_URL must point to localhost for offline-first policy")

    def generate(self, system_prompt: str, task_prompt: str) -> str:
        self._validate()
        try:
            payload = {
                "model": self.model,
                "system": system_prompt,
                "prompt": task_prompt,
                "stream": False,
            }
            out = self._request_json("/api/generate", payload=payload)
            answer = (out.get("response") or "").strip()
            if not answer:
                raise RuntimeError("Ollama returned empty response")
            return answer
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama unavailable at {self.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from Ollama: {exc}") from exc

    def healthcheck(self) -> dict:
        try:
            self._validate()
            out = self._request_json("/api/tags")
            models = [m.get("name", "") for m in out.get("models", [])]
            return {
                "ok": True,
                "adapter": self.name,
                "base_url": self.base_url,
                "model": self.model,
                "model_available": self.model in models,
                "offline": True,
            }
        except Exception as exc:
            return {"ok": False, "adapter": self.name, "error": str(exc), "offline": True}


class MlxAdapter:
    name = "mlx"

    def __init__(self, model: str | None = None, timeout: int | None = None) -> None:
        self.model = (model or os.environ.get("HATORI_MLX_MODEL") or "").strip()
        self.timeout = int((str(timeout) if timeout is not None else (os.environ.get("HATORI_MLX_TIMEOUT_S") or "60")).strip())
        self.max_tokens = int((os.environ.get("HATORI_MLX_MAX_TOKENS") or "512").strip())
        self.temperature = float((os.environ.get("HATORI_MLX_TEMPERATURE") or "0.2").strip())

    def _validate(self) -> None:
        if not self.model:
            raise RuntimeError("HATORI_MLX_MODEL is required for MLX backend")
        if not shutil.which("python3"):
            raise RuntimeError("python3 not found for MLX backend")

    def _run_mlx(self, prompt: str) -> str:
        code = (
            "import sys\n"
            "from mlx_lm import load, generate\n"
            "model_id = sys.argv[1]\n"
            "max_tokens = int(sys.argv[2])\n"
            "temperature = float(sys.argv[3])\n"
            "prompt = sys.argv[4]\n"
            "model, tokenizer = load(model_id)\n"
            "out = generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, temp=temperature, verbose=False)\n"
            "print(out if isinstance(out, str) else str(out))\n"
        )
        proc = subprocess.run(
            ["python3", "-c", code, self.model, str(self.max_tokens), str(self.temperature), prompt],
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip() or "mlx generation failed"
            raise RuntimeError(err)
        return proc.stdout.strip()

    def generate(self, system_prompt: str, task_prompt: str) -> str:
        self._validate()
        prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{task_prompt}\n\n[ASSISTANT]\n"
        out = self._run_mlx(prompt)
        if not out:
            raise RuntimeError("MLX returned empty response")
        return out

    def healthcheck(self) -> dict:
        try:
            self._validate()
            check_code = "import mlx_lm; print('ok')"
            proc = subprocess.run(["python3", "-c", check_code], capture_output=True, text=True, timeout=10)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or "mlx_lm import failed")
            return {"ok": True, "adapter": self.name, "model": self.model, "offline": True}
        except Exception as exc:
            return {"ok": False, "adapter": self.name, "error": str(exc), "offline": True}


def prefer_ollama_if_available(base_url: str | None = None, timeout: int = 2) -> bool:
    url = (base_url or os.environ.get("HATORI_OLLAMA_URL") or "http://127.0.0.1:11434").strip().rstrip("/")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        return False
    req = urllib.request.Request(f"{url}/api/tags", headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _ = resp.read()
        return True
    except Exception:
        return False


def get_model_adapter() -> ModelAdapter:
    mode = os.environ.get("HATORI_MODEL", "none").strip().lower()
    if mode == "ollama":
        return OllamaAdapter()
    if mode == "llamacpp":
        return LlamaCppAdapter()
    if mode == "mlx":
        return MlxAdapter()
    if mode in {"none", ""}:
        return NullAdapter()
    raise RuntimeError(f"Unsupported HATORI_MODEL value: {mode}")


def _route_env_key(task: str, suffix: str) -> str:
    safe = task.upper().replace("-", "_")
    return f"HATORI_ROUTE_{safe}_{suffix}"


def _route_defaults(task: str) -> dict:
    # Backward-compatible defaults; final routing should be set in hatori.env.
    defaults = {
        "reply_write": {
            "backend": "ollama",
            "model": os.environ.get("HATORI_OLLAMA_MODEL", "llama3.2:3b"),
            "fallback_backend": "none",
            "fallback_model": "",
        },
        "plan_write": {
            "backend": "ollama",
            "model": os.environ.get("HATORI_OLLAMA_MODEL", "llama3.2:3b"),
            "fallback_backend": "none",
            "fallback_model": "",
        },
        "rewrite_polish": {
            "backend": "ollama",
            "model": os.environ.get("HATORI_OLLAMA_MODEL", "llama3.2:3b"),
            "fallback_backend": "none",
            "fallback_model": "",
        },
        "classify_intent": {
            "backend": "ollama",
            "model": "llama3.2:1b",
            "fallback_backend": "none",
            "fallback_model": "",
        },
        "extract_fields": {
            "backend": "ollama",
            "model": "llama3.2:1b",
            "fallback_backend": "none",
            "fallback_model": "",
        },
        "context_pack": {
            "backend": "ollama",
            "model": "llama3.2:1b",
            "fallback_backend": "none",
            "fallback_model": "",
        },
        "retrieval_query_build": {
            "backend": "ollama",
            "model": "llama3.2:1b",
            "fallback_backend": "none",
            "fallback_model": "",
        },
        "edit_pattern_cluster": {
            "backend": "ollama",
            "model": "llama3.2:1b",
            "fallback_backend": "none",
            "fallback_model": "",
        },
        "answer_score": {
            "backend": "ollama",
            "model": "llama3.2:3b",
            "fallback_backend": "ollama",
            "fallback_model": "gemma2:2b",
        },
        "quality_gate": {
            "backend": "ollama",
            "model": "llama3.2:3b",
            "fallback_backend": "ollama",
            "fallback_model": "gemma2:2b",
        },
    }
    return defaults.get(task, defaults["reply_write"])


def _resolve_route(task: str) -> dict:
    d = _route_defaults(task)
    backend = (os.environ.get(_route_env_key(task, "BACKEND")) or d["backend"] or "none").strip().lower()
    model = (os.environ.get(_route_env_key(task, "MODEL")) or d["model"] or "").strip()
    fb_backend = (os.environ.get(_route_env_key(task, "FALLBACK_BACKEND")) or d["fallback_backend"] or "none").strip().lower()
    fb_model = (os.environ.get(_route_env_key(task, "FALLBACK_MODEL")) or d["fallback_model"] or "").strip()
    return {
        "task": task,
        "backend": backend,
        "model": model,
        "fallback_backend": fb_backend,
        "fallback_model": fb_model,
    }


def _adapter_from_backend(backend: str, model: str) -> ModelAdapter:
    b = (backend or "").strip().lower()
    if b == "ollama":
        return OllamaAdapter(model=model or None)
    if b == "mlx":
        if (os.environ.get("HATORI_DISABLE_MLX") or "").strip() == "1":
            raise RuntimeError("MLX disabled by HATORI_DISABLE_MLX=1")
        return MlxAdapter(model=model or None)
    if b == "llamacpp":
        return LlamaCppAdapter()
    if b == "none":
        return NullAdapter()
    raise RuntimeError(f"unsupported backend: {backend}")


def get_task_model_adapter(task: str) -> tuple[ModelAdapter | None, str | None, dict]:
    explicit_mode = (os.environ.get("HATORI_MODEL") or "").strip().lower()
    if explicit_mode:
        try:
            adapter = get_model_adapter()
            return adapter, None, {
                "task": task,
                "backend_used": adapter.name,
                "fallback_used": False,
                "route": "explicit_HATORI_MODEL",
            }
        except Exception as exc:
            return None, str(exc), {"task": task, "backend_used": "none", "fallback_used": False, "route": "explicit_HATORI_MODEL"}

    route = _resolve_route(task)
    errors: list[str] = []

    for idx, (backend, model) in enumerate(
        [
            (route["backend"], route["model"]),
            (route["fallback_backend"], route["fallback_model"]),
        ]
    ):
        if not backend or backend == "none":
            continue
        try:
            adapter = _adapter_from_backend(backend, model)
            health = adapter.healthcheck()
            if not health.get("ok"):
                raise RuntimeError(str(health.get("error") or f"{backend} healthcheck failed"))
            if adapter.name == "ollama" and health.get("model_available") is False:
                raise RuntimeError(f"ollama model not available: {getattr(adapter, 'model', '')}")
            return adapter, None, {
                "task": task,
                "backend_used": adapter.name,
                "model_used": getattr(adapter, "model", ""),
                "fallback_used": idx > 0,
                "route": route,
            }
        except Exception as exc:
            errors.append(f"{backend}: {exc}")

    if prefer_ollama_if_available():
        adapter = OllamaAdapter()
        return adapter, None, {
            "task": task,
            "backend_used": adapter.name,
            "model_used": adapter.model,
            "fallback_used": True,
            "route": "legacy_ollama_probe",
        }

    return None, "Ollama not running; start it via brew services start ollama.", {
        "task": task,
        "backend_used": "none",
        "fallback_used": False,
        "route": route,
    }
