import hashlib
import math
import os
import re
from typing import Protocol


class EmbeddingsAdapter(Protocol):
    name: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class HashEmbeddingAdapter:
    """Deterministic local embedding adapter for offline-first CI-safe runs."""

    name = "hash-v1"

    def __init__(self, dimension: int = 192) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension

    @staticmethod
    def _normalize_token(token: str) -> str:
        synonyms = {
            "car": "automobile",
            "cars": "automobile",
            "vehicle": "automobile",
            "vehicles": "automobile",
            "upkeep": "maintenance",
            "maintain": "maintenance",
            "plan": "schedule",
            "steps": "checklist",
            "todo": "checklist",
            "backup": "snapshot",
        }
        return synonyms.get(token, token)

    @staticmethod
    def _tokens(text: str) -> list[str]:
        base = [t for t in re.findall(r"[A-Za-z0-9_]+", text.lower()) if len(t) >= 2]
        normalized = [HashEmbeddingAdapter._normalize_token(t) for t in base]
        trigrams: list[str] = []
        joined = " ".join(normalized)
        for i in range(max(0, len(joined) - 2)):
            gram = joined[i : i + 3]
            if gram.strip():
                trigrams.append(f"g:{gram}")
        return normalized + trigrams

    def _hash_index(self, token: str, salt: str) -> int:
        dig = hashlib.blake2b(f"{salt}:{token}".encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(dig, byteorder="big", signed=False) % self.dimension

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        tokens = self._tokens(text)
        if not tokens:
            return vec

        for tok in tokens:
            idx = self._hash_index(tok, "idx")
            sign = 1.0 if (self._hash_index(tok, "sgn") % 2 == 0) else -1.0
            vec[idx] += sign

        norm = math.sqrt(sum(v * v for v in vec))
        if norm <= 0:
            return vec
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


class SentenceTransformersAdapter:
    name = "sentence-transformers"

    def __init__(self, model_path: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "sentence-transformers adapter requested but dependency is missing. "
                "Install requirements and provide a local model path."
            ) from exc

        self._model = SentenceTransformer(model_path, local_files_only=True)
        dim = self._model.get_sentence_embedding_dimension()
        if dim is None:
            raise RuntimeError("Could not determine sentence-transformers embedding dimension")
        self.dimension = int(dim)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in row] for row in vectors]


def get_embeddings_adapter() -> EmbeddingsAdapter:
    backend = os.environ.get("HATORI_EMBED_BACKEND", "hash").strip().lower()
    model_path = os.environ.get("HATORI_EMBED_MODEL_PATH", "").strip()
    if backend in {"st", "sentence-transformers"}:
        if not model_path:
            raise RuntimeError("HATORI_EMBED_MODEL_PATH is required for sentence-transformers backend")
        return SentenceTransformersAdapter(model_path=model_path)
    return HashEmbeddingAdapter()
