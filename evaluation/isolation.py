"""
Isolation primitives for the evaluation layer.

Guarantees:
    1. Every file the evaluation layer writes resolves under evaluation/
       (guarded — a write outside raises IsolationError).
    2. Experiments run in disposable per-experiment workspaces.
    3. RAG used by experiments is either read-only (production store) or a
       deterministically seeded isolated store — production chroma_data is
       never mutated.
    4. Model overrides for model-comparison experiments are injected into
       the in-process llm role singletons only, and restored afterwards.
    5. Production log writers (logs/prompts, logs/raw_llm) are redirected to
       the experiment workspace during runs.
"""

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from evaluation.config import EVAL_ROOT, RESULTS_DIR, REPORTS_DIR, GENERATED_DATASETS_DIR


class IsolationError(RuntimeError):
    """Raised when the evaluation layer would write outside evaluation/."""


def ensure_under_evaluation(path: Path) -> Path:
    """Resolve `path` and refuse anything outside the evaluation root."""
    resolved = Path(path).resolve()
    if not str(resolved).startswith(str(EVAL_ROOT.resolve())):
        raise IsolationError(
            f"Refusing to write outside the evaluation layer: {resolved}"
        )
    return resolved


def new_experiment_dir(name: str, uid: str) -> Path:
    """Create and return an append-only results directory for one experiment."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    exp_dir = ensure_under_evaluation(RESULTS_DIR / f"{name}_{uid}")
    exp_dir.mkdir(parents=True, exist_ok=False)  # never overwrite
    (exp_dir / "samples").mkdir()
    return exp_dir


def new_workspace(uid: str) -> Path:
    """Create a disposable per-experiment working directory."""
    ws = ensure_under_evaluation(Path(tempfile.mkdtemp(prefix=f"eval_ws_{uid}_", dir=EVAL_ROOT)))
    return ws


def cleanup_workspace(ws: Path) -> None:
    shutil.rmtree(ws, ignore_errors=True)


# ── RAG isolation ─────────────────────────────────────────────────────────

def isolated_rag(uid: str):
    """A fresh RAGMemory bound to an evaluation-owned directory.

    Never touches production chroma_data.
    """
    from utils.rag import RAGMemory

    store = new_workspace(f"rag_{uid}") / "chroma"
    return RAGMemory(persist_directory=str(store))


# ── Model override (in-process only) ──────────────────────────────────────

@contextmanager
def model_override(role: str, model: str):
    """
    Temporarily bind `role` to an OpenRouterService with `model`.

    Only the in-process singleton registry is touched; no configuration or
    file is modified. Used exclusively by model-comparison experiments.
    """
    from llm import OpenRouterService

    import llm.service as svc

    original = svc._services.get(role)
    svc._services[role] = OpenRouterService(role=role, model=model)
    try:
        yield
    finally:
        if original is None:
            svc._services.pop(role, None)
        else:
            svc._services[role] = original


@contextmanager
def production_log_redirect(workspace: Path):
    """
    Redirect production prompt/raw-response log writers to the experiment
    workspace so evaluation runs leave production logs/ untouched.
    """
    from agents import test_writer as tw

    target = ensure_under_evaluation(workspace / "llm_logs")
    target.mkdir(parents=True, exist_ok=True)

    def _save_prompt_log(filename, system_prompt, user_prompt, attempt, _target=target):
        log_path = _target / "prompts" / f"{filename}_attempt{attempt}.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "=== SYSTEM PROMPT ===\n" + system_prompt + "\n=== USER PROMPT ===\n" + user_prompt,
            encoding="utf-8",
        )

    def _save_raw_response_log(filename, raw_response, attempt, _target=target):
        log_path = _target / "raw_llm" / f"{filename}_attempt{attempt}.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("=== RAW RESPONSE ===\n" + raw_response, encoding="utf-8")

    with (
        patch.object(tw, "save_prompt_log", _save_prompt_log),
        patch.object(tw, "save_raw_response_log", _save_raw_response_log),
    ):
        yield
