import os
import re
import time
import urllib.request
import urllib.parse
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any

from hatori.backends.mlx_backend import MlxBackend
from hatori.embeddings import get_embeddings_adapter
from hatori.model import OllamaAdapter

DEFAULT_EMBEDDING_MODEL_ID = (os.environ.get("HATORI_EMBEDDING_MODEL_ID") or "current-default").strip()
DEFAULT_EMBEDDING_INDEX_VERSION = (os.environ.get("HATORI_EMBEDDING_INDEX_VERSION") or "v1").strip()
UUID_ANY_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)
FORBIDDEN_MARKERS = ["emb:", "artefact_id", "user request:", "task prompt", "retrieved pks", "required behaviour"]


@dataclass
class GatewayError:
    backend: str
    code: str
    message: str


@dataclass
class GatewayResult:
    text: str
    backend_used: str
    backend_fallback_used: bool
    latency_ms: int
    errors: list[dict[str, str]]


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    embedding_model_id: str
    embedding_index_version: str


class _OllamaBackend:
    name = "ollama"

    def __init__(self) -> None:
        self.adapter = OllamaAdapter()
        self.availability_timeout_s = float((os.environ.get("HATORI_GATEWAY_AVAIL_TIMEOUT_S") or "2").strip())

    def healthcheck(self, timeout_s: float | None = None) -> tuple[bool, str]:
        timeout = float(timeout_s if timeout_s is not None else self.availability_timeout_s)
        try:
            base = self.adapter.base_url.rstrip("/")
            parsed = urllib.parse.urlparse(base)
            if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
                return False, "ollama url must be localhost"
            req = urllib.request.Request(f"{base}/api/tags", headers={"Accept": "application/json"}, method="GET")
            with urllib.request.urlopen(req, timeout=max(0.5, timeout)):
                pass
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def generate(self, prompt: str, timeout_s: float | None = None) -> str:
        return self.adapter.generate(system_prompt="", task_prompt=prompt)


class _Breaker:
    def __init__(self) -> None:
        self.threshold = int((os.environ.get("HATORI_BREAKER_FAILURES") or "3").strip())
        self.window_s = int((os.environ.get("HATORI_BREAKER_WINDOW_S") or "120").strip())
        self.cooldown_s = int((os.environ.get("HATORI_BREAKER_COOLDOWN_S") or "120").strip())
        self.failures: dict[str, list[float]] = {}
        self.open_until: dict[str, float] = {}

    def _now(self) -> float:
        return time.time()

    def is_open(self, backend: str) -> bool:
        now = self._now()
        return self.open_until.get(backend, 0) > now

    def record_success(self, backend: str) -> None:
        self.failures.pop(backend, None)
        self.open_until.pop(backend, None)

    def record_failure(self, backend: str) -> None:
        now = self._now()
        values = [t for t in self.failures.get(backend, []) if now - t <= self.window_s]
        values.append(now)
        self.failures[backend] = values
        if len(values) >= self.threshold:
            self.open_until[backend] = now + self.cooldown_s
            self.failures[backend] = []

    def state(self) -> dict[str, Any]:
        now = self._now()
        return {
            backend: {
                "open": until > now,
                "open_until_epoch": int(until) if until > now else 0,
            }
            for backend, until in self.open_until.items()
        }


_GLOBAL_BREAKER = _Breaker()


class ModelGateway:
    def __init__(self, backends: dict[str, Any] | None = None) -> None:
        self._backends = backends or {
            "mlx": MlxBackend(),
            "ollama": _OllamaBackend(),
        }
        self._last_result: GatewayResult | None = None

    @property
    def last_result(self) -> GatewayResult | None:
        return self._last_result

    def _order(self) -> list[str]:
        raw = (os.environ.get("HATORI_GENERATOR_ORDER") or "mlx,ollama").strip().lower()
        order = [x.strip() for x in raw.split(",") if x.strip()]
        return order or ["mlx", "ollama"]

    def _clean_error(self, lang: str | None, prompt: str) -> str:
        l = (lang or "").strip().lower()
        if not l:
            l = "hu" if "respond in hungarian" in prompt.lower() else "en"
        if l == "hu":
            return "Nem tudok most válaszolni, mert a helyi modell nem elérhető. Indítsd el az Ollama/MLX szolgáltatást."
        return "I cannot answer right now because the local model is unavailable. Start the local Ollama/MLX service and retry."

    def _validate_user_output(self, text: str) -> bool:
        lowered = (text or "").lower()
        if not lowered.strip():
            return False
        if UUID_ANY_RE.search(lowered):
            return False
        return not any(m in lowered for m in FORBIDDEN_MARKERS)

    def generate(
        self,
        prompt: str,
        *,
        conversation_id: str | None = None,
        lang: str | None = None,
        mode: str | None = None,
        timeout_s: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GatewayResult:
        del conversation_id, mode, metadata
        start_all = time.perf_counter()
        errors: list[GatewayError] = []
        attempted = 0
        for backend_name in self._order():
            backend = self._backends.get(backend_name)
            if backend is None:
                errors.append(GatewayError(backend_name, "unknown_backend", "unknown backend in order"))
                continue
            if _GLOBAL_BREAKER.is_open(backend_name):
                errors.append(GatewayError(backend_name, "breaker_open", "backend temporarily disabled"))
                continue
            ok, detail = backend.healthcheck(timeout_s=timeout_s)
            if not ok:
                _GLOBAL_BREAKER.record_failure(backend_name)
                errors.append(GatewayError(backend_name, "unavailable", detail or "backend unavailable"))
                continue
            attempted += 1
            try:
                out = backend.generate(prompt=prompt, timeout_s=timeout_s).strip()
                if not self._validate_user_output(out):
                    raise RuntimeError("invalid or unsafe output")
                _GLOBAL_BREAKER.record_success(backend_name)
                result = GatewayResult(
                    text=out,
                    backend_used=backend_name,
                    backend_fallback_used=len(errors) > 0,
                    latency_ms=int((time.perf_counter() - start_all) * 1000),
                    errors=[asdict(e) for e in errors],
                )
                self._last_result = result
                return result
            except Exception as exc:
                _GLOBAL_BREAKER.record_failure(backend_name)
                errors.append(GatewayError(backend_name, "generate_failed", str(exc)))

        result = GatewayResult(
            text=self._clean_error(lang=lang, prompt=prompt),
            backend_used="none",
            backend_fallback_used=len(errors) > 0,
            latency_ms=int((time.perf_counter() - start_all) * 1000),
            errors=[asdict(e) for e in errors],
        )
        self._last_result = result
        return result

    def embed(
        self,
        texts: list[str],
        *,
        embedding_model_id: str | None = None,
        timeout_s: float | None = None,
    ) -> EmbeddingResult:
        del timeout_s
        adapter = get_embeddings_adapter()
        vectors = adapter.embed(texts)
        model_id = (embedding_model_id or DEFAULT_EMBEDDING_MODEL_ID).strip() or DEFAULT_EMBEDDING_MODEL_ID
        return EmbeddingResult(
            vectors=vectors,
            embedding_model_id=model_id,
            embedding_index_version=DEFAULT_EMBEDDING_INDEX_VERSION,
        )

    def health_status(self) -> dict[str, Any]:
        mlx = self._backends.get("mlx")
        ollama = self._backends.get("ollama")
        mlx_ok, mlx_detail = (False, "not configured") if mlx is None else mlx.healthcheck()
        ollama_ok, ollama_detail = (False, "not configured") if ollama is None else ollama.healthcheck()
        breaker_state = _GLOBAL_BREAKER.state()
        return {
            "generator_order": self._order(),
            "generator_backends": {
                "mlx": {"available": mlx_ok, "detail": mlx_detail},
                "ollama": {"available": ollama_ok, "detail": ollama_detail},
            },
            "breaker": {
                "mlx": breaker_state.get("mlx", {"open": False, "open_until_epoch": 0}),
                "ollama": breaker_state.get("ollama", {"open": False, "open_until_epoch": 0}),
            },
        }


class GatewayModelAdapter:
    name = "gateway"

    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway or ModelGateway()
        self.last_backend_used = "none"
        self.last_backend_fallback_used = False

    def generate(self, system_prompt: str, task_prompt: str) -> str:
        prompt = f"{system_prompt}\n\n{task_prompt}".strip()
        result = self.gateway.generate(prompt=prompt)
        self.last_backend_used = result.backend_used
        self.last_backend_fallback_used = result.backend_fallback_used
        return result.text


def get_gateway_model_adapter() -> GatewayModelAdapter:
    return GatewayModelAdapter()


def get_model_gateway() -> ModelGateway:
    return ModelGateway()
