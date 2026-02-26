import hashlib
import os
from pathlib import Path
import subprocess
from typing import Protocol
import shutil


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
        return (
            "Offline deterministic response (NullAdapter). "
            f"Request fingerprint: {digest}. "
            "Set HATORI_MODEL=llamacpp with a local GGUF model to enable full generation."
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


def get_model_adapter() -> ModelAdapter:
    mode = os.environ.get("HATORI_MODEL", "none").strip().lower()
    if mode == "llamacpp":
        return LlamaCppAdapter()
    if mode in {"none", ""}:
        return NullAdapter()
    raise RuntimeError(f"Unsupported HATORI_MODEL value: {mode}")
