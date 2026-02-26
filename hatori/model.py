import hashlib
import os
from pathlib import Path
import subprocess
from typing import Protocol


class ModelAdapter(Protocol):
    name: str

    def generate(self, system_prompt: str, task_prompt: str) -> str:
        ...

    def healthcheck(self) -> dict:
        ...


class NullAdapter:
    name = "none"

    def generate(self, system_prompt: str, task_prompt: str) -> str:
        digest = hashlib.sha256((system_prompt + "\n" + task_prompt).encode("utf-8")).hexdigest()[:12]
        return f"[null-adapter:{digest}] Offline deterministic draft."

    def healthcheck(self) -> dict:
        return {"ok": True, "adapter": self.name, "offline": True}


class LlamaCppAdapter:
    name = "llamacpp"

    def __init__(self) -> None:
        self.model_path = os.environ.get("HATORI_LLAMACPP_MODEL_PATH", "").strip()
        self.binary = os.environ.get("HATORI_LLAMACPP_BIN", "llama-cli").strip()
        self.max_tokens = int(os.environ.get("HATORI_LLAMACPP_MAX_TOKENS", "192"))

    def _validate(self) -> None:
        if not self.model_path:
            raise RuntimeError("HATORI_LLAMACPP_MODEL_PATH is required for HATORI_MODEL=llamacpp")
        if not Path(self.model_path).exists():
            raise RuntimeError(f"Llama model file not found: {self.model_path}")

    def generate(self, system_prompt: str, task_prompt: str) -> str:
        self._validate()
        prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{task_prompt}\n<|assistant|>\n"
        cmd = [
            self.binary,
            "-m",
            self.model_path,
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
                "offline": True,
            }
        except Exception as exc:
            return {"ok": False, "adapter": self.name, "error": str(exc), "offline": True}


def get_model_adapter() -> ModelAdapter:
    mode = os.environ.get("HATORI_MODEL", "none").strip().lower()
    if mode == "llamacpp":
        return LlamaCppAdapter()
    if mode in {"none", ""}:
        return NullAdapter()
    raise RuntimeError(f"Unsupported HATORI_MODEL value: {mode}")
