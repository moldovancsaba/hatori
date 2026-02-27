import os
import subprocess
import sys
import time


class MlxBackend:
    name = "mlx"

    def __init__(self) -> None:
        self.model = (os.environ.get("HATORI_MLX_MODEL") or "").strip()
        self.timeout_s = float((os.environ.get("HATORI_MLX_TIMEOUT_S") or "30").strip())

    def _python_has_mlx(self, timeout_s: float) -> tuple[bool, str]:
        start = time.perf_counter()
        cmd = [
            sys.executable,
            "-c",
            "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('mlx_lm') else 1)",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=max(1.0, timeout_s))
        except subprocess.TimeoutExpired:
            elapsed = int((time.perf_counter() - start) * 1000)
            return False, f"mlx import check timeout ({elapsed}ms)"
        ok = proc.returncode == 0
        return ok, ("" if ok else "mlx_lm not installed")

    def healthcheck(self, timeout_s: float | None = None) -> tuple[bool, str]:
        timeout = float(timeout_s if timeout_s is not None else self.timeout_s)
        if not self.model:
            return False, "HATORI_MLX_MODEL not set"
        dep = self._python_has_mlx(timeout)
        if not dep[0]:
            return dep
        return True, "configured"

    def generate(self, prompt: str, timeout_s: float | None = None) -> str:
        timeout = float(timeout_s if timeout_s is not None else self.timeout_s)
        if not self.model:
            raise RuntimeError("HATORI_MLX_MODEL not set")
        # Use mlx-lm Python module in subprocess to keep gateway resilient to import/runtime failures.
        script = (
            "import argparse,sys\n"
            "from mlx_lm import load, generate\n"
            "p=argparse.ArgumentParser(); p.add_argument('--model'); p.add_argument('--max-tokens',type=int,default=256); p.add_argument('--prompt')\n"
            "a=p.parse_args()\n"
            "model, tok = load(a.model)\n"
            "out = generate(model, tok, prompt=a.prompt, max_tokens=a.max_tokens)\n"
            "print((out or '').strip())\n"
        )
        max_tokens = int((os.environ.get("HATORI_MLX_MAX_TOKENS") or "256").strip())
        cmd = [
            sys.executable,
            "-c",
            script,
            "--model",
            self.model,
            "--max-tokens",
            str(max_tokens),
            "--prompt",
            prompt,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=max(1.0, timeout))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"mlx timeout after {timeout}s") from exc
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "mlx generation failed").strip()
            raise RuntimeError(err)
        answer = (proc.stdout or "").strip()
        if not answer:
            raise RuntimeError("mlx returned empty response")
        return answer
