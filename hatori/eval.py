"""
Evaluation — implementation of docs/10-api-contracts/interfaces.md.
EVAL.run_golden_tests(subset=None) -> pass/fail + reasons.
EVAL.run_rag_eval_suite() -> pass/fail for retrieval eval (tests/rag_eval).
"""
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]  # repo root (parent of hatori package)
GOLDEN_SCRIPT = ROOT / "tests" / "golden" / "run_golden.py"
RAG_EVAL_SCRIPT = ROOT / "tests" / "rag_eval" / "run_rag_eval.py"


def run_golden_tests(subset: int | None = None) -> dict[str, Any]:
    """
    Run golden test suite. Returns pass/fail and reasons.
    subset: if set, run only the first N tests (0 = all).
    """
    if not GOLDEN_SCRIPT.is_file():
        return {
            "ok": False,
            "reason": f"Golden script not found: {GOLDEN_SCRIPT}",
            "passed": 0,
            "failed": 0,
        }
    args = [sys.executable, str(GOLDEN_SCRIPT)]
    if subset is not None and subset > 0:
        args.extend(["--subset", str(subset)])
    proc = subprocess.run(
        args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    reasons = (proc.stderr or "").strip() or (proc.stdout or "").strip()
    return {
        "ok": proc.returncode == 0,
        "reason": reasons or ("PASS" if proc.returncode == 0 else "FAIL"),
        "returncode": proc.returncode,
    }


def run_rag_eval_suite() -> dict[str, Any]:
    """
    Run RAG retrieval eval (tests/rag_eval). Expects DB already migrated/seeded.
    """
    if not RAG_EVAL_SCRIPT.is_file():
        return {
            "ok": False,
            "reason": f"RAG eval script not found: {RAG_EVAL_SCRIPT}",
            "returncode": -1,
        }
    proc = subprocess.run(
        [sys.executable, str(RAG_EVAL_SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    reasons = (proc.stderr or "").strip() or (proc.stdout or "").strip()
    return {
        "ok": proc.returncode == 0,
        "reason": reasons or ("PASS" if proc.returncode == 0 else "FAIL"),
        "returncode": proc.returncode,
    }
