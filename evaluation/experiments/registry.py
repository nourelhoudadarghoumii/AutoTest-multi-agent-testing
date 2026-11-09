"""
Concrete experiment definitions.

BASELINE      — production model + P0 prompt + production RAG (read-only)
PROMPTS       — P0 vs P1 vs P2 vs P3 (model & dataset identical)
RAG A/B       — P3 with RAG OFF vs P3 with RAG ON (seeded isolated store)
MODELS        — candidate writer models vs baseline, same prompt/dataset
DEBUGGER      — controlled repair scenarios through the production debugger
"""

import json
import shutil
import time
import uuid
from pathlib import Path

from evaluation.config import (
    DEBUGGER_TEMPERATURE,
    MAX_TOKENS,
    PAUSE_BETWEEN_LLM_CALLS,
    environment_metadata,
)
from evaluation.datasets.build import dataset_fingerprint, dataset_root
from evaluation.datasets.corpus import ALL_SAMPLES, PATTERN_CORPUS, get_sample
from evaluation.experiments.prompts import PROMPT_VERSIONS
from evaluation.experiments.runner import run_writer_experiment
from evaluation.isolation import isolated_rag, model_override, new_experiment_dir, new_workspace, production_log_redirect
from evaluation.metrics.aggregate import aggregate_debugger_results, write_aggregated
from evaluation.metrics.debug import measure_debug_repair
from evaluation.metrics.retrieval import measure_retrieval
from evaluation.security import write_json_scrubbed

DEFAULT_DEBUGGER_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
DEFAULT_WRITER_MODEL = "cohere/north-mini-code:free"


# ── 1. Baseline ───────────────────────────────────────────────────────────

def run_baseline(mutation: bool = False, sample_ids: list[str] | None = None,
                 writer_model: str | None = None, notes: str = "") -> Path:
    """Current production setup: fixed model, P0 prompt, production RAG read."""
    return run_writer_experiment(
        name="baseline",
        prompt_version="P0",
        rag_enabled=False,  # P0 production prompt carries no RAG section by default
        writer_model=writer_model,
        mutation=mutation,
        sample_ids=sample_ids,
        notes=notes or "production configuration, no variable changed",
    )


# ── 2. Prompt engineering ─────────────────────────────────────────────────

def run_prompt_variants(mutation: bool = False, sample_ids: list[str] | None = None,
                        versions: tuple = PROMPT_VERSIONS, writer_model: str | None = None) -> list[Path]:
    """P0 / P1 / P2 / P3 — identical model, dataset and execution environment."""
    dirs = []
    for version in versions:
        dirs.append(run_writer_experiment(
            name=f"prompt_{version.lower()}",
            prompt_version=version,
            rag_enabled=False,  # RAG is held constant (OFF) across prompt variants;
                                # P3-vs-P2 with RAG ON is the dedicated RAG experiment
            writer_model=writer_model,
            mutation=mutation,
            sample_ids=sample_ids,
            notes=f"prompt engineering: {version} (one variable: prompt)",
        ))
    return dirs


# ── 3. RAG A/B ────────────────────────────────────────────────────────────

def _seed_rag(store):
    """Seed an isolated RAG store with the corpus patterns (deterministic)."""
    for pattern in PATTERN_CORPUS:
        store.store_pattern(
            function_name=pattern["function_name"],
            function_signature=pattern["function_signature"],
            error_type=pattern["error_type"],
            root_cause=pattern["root_cause"],
            fix_applied=pattern["fix_applied"],
            complexity=0.0,
        )
    return store


def run_rag_ab(mutation: bool = False, sample_ids: list[str] | None = None) -> list[Path]:
    """
    RAG OFF vs RAG ON with P3 (structured + few-shot), everything else
    identical. The ON store is isolated and deterministically seeded, so
    the retrieval content is reproducible.
    """
    uid = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    rag_store = _seed_rag(isolated_rag(uid))

    dirs = [
        run_writer_experiment(
            name="rag_off",
            prompt_version="P3", rag_enabled=False,
            mutation=mutation, sample_ids=sample_ids,
            notes="RAG A/B: P3 without retrieved patterns",
        ),
        run_writer_experiment(
            name="rag_on",
            prompt_version="P3", rag_enabled=True, rag_memory=rag_store,
            mutation=mutation, sample_ids=sample_ids,
            notes="RAG A/B: P3 with seeded bug patterns retrieved",
        ),
    ]
    return dirs


def run_retrieval_evaluation() -> Path:
    """
    Retrieval-only evaluation of the RAG store against the labeled corpus:
    Recall@K, Precision@K, MRR, nDCG.
    """
    uid = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    store = _seed_rag(isolated_rag(uid))

    queries = []
    for sample in ALL_SAMPLES:
        if not sample.is_debug_target:
            continue
        retrieved = store.retrieve_similar_patterns(
            function_name=sample.target_function,
            function_signature=f"def {sample.target_function}(...)",
            complexity=0.0,
            n_results=3,
        )
        queries.append({
            "function_name": sample.target_function,
            "function_signature": f"def {sample.target_function}(...)",
            "relevant": set(sample.relevant_pattern_functions),
            "retrieved": [r.get("function", "") for r in retrieved],
        })

    metrics = measure_retrieval(queries)
    metrics["seeded_patterns"] = [p["function_name"] for p in PATTERN_CORPUS]
    metrics["per_query"] = [
        {k: (sorted(v) if isinstance(v, set) else v) for k, v in q.items()}
        for q in queries
    ]

    exp_dir = new_experiment_dir("retrieval", uid)
    write_json_scrubbed(exp_dir / "metadata.json", {
        "experiment": "retrieval",
        "experiment_id": exp_dir.name,
        "k": metrics["k"],
        "dataset_version": "v1",
        "dataset_hash": dataset_fingerprint(),
        "rag_store": "isolated_seeded",
        **environment_metadata(),
    })
    write_json_scrubbed(exp_dir / "aggregated.json", metrics)
    return exp_dir


# ── 4. Model comparison framework ─────────────────────────────────────────

def run_model_comparison(
    writer_models: list[str],
    mutation: bool = False,
    sample_ids: list[str] | None = None,
    notes: str = "",
) -> list[Path]:
    """
    Compare candidate Test Writer models under IDENTICAL conditions
    (P0 production prompt, same dataset, same caps).

    No winner is selected automatically — tables are produced for analysis.
    """
    dirs = []
    for model in writer_models:
        dirs.append(run_writer_experiment(
            name=f"model_{model.replace('/', '_').replace(':', '-')}",
            prompt_version="P0",
            rag_enabled=False,
            writer_model=model,
            mutation=mutation,
            sample_ids=sample_ids,
            notes=notes or f"model comparison candidate: {model}",
        ))
    return dirs


# ── 5. Debugger experiment ────────────────────────────────────────────────

def run_debugger_experiment(
    debugger_model: str | None = None,
    sample_ids: list[str] | None = None,
    max_iterations: int = 3,
    notes: str = "",
) -> Path:
    """
    Controlled debugging scenarios through the production debugger
    (DebuggerLLM + apply_fix_safely) in isolated workspaces.

    Measures: repair success, test recovery, first-attempt repair,
    regression rate, iterations, latency.
    """
    from agents.debugger import DebuggerLLM  # noqa: F401 — production import
    from llm import ROLE_DEBUGGER

    uid = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    exp_dir = new_experiment_dir("debugger", uid)
    workspace = new_workspace(uid)

    debug_samples = [s for s in ALL_SAMPLES if s.is_debug_target]
    if sample_ids:
        debug_samples = [get_sample(sid) for sid in sample_ids]

    # Token accounting: wrap the service singleton with a recording proxy
    usage = {"prompt": 0, "completion": 0, "calls": 0}

    class _RecordingService:
        def __init__(self, inner):
            self._inner = inner
            self.model = inner.model

        def complete(self, *args, **kwargs):
            response = self._inner.complete(*args, **kwargs)
            usage["prompt"] += response.prompt_tokens
            usage["completion"] += response.completion_tokens
            usage["calls"] += 1
            return response

    production = DebuggerLLM  # class reference; instantiate per sample

    effective_model = debugger_model or DEFAULT_DEBUGGER_MODEL

    metadata = {
        "experiment": "debugger",
        "experiment_id": exp_dir.name,
        "model": effective_model,
        "model_overridden": debugger_model is not None,
        "debugger_temperature": DEBUGGER_TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "max_iterations": max_iterations,
        "dataset_version": "v1",
        "dataset_hash": dataset_fingerprint(),
        "sample_ids": [s.sample_id for s in debug_samples],
        "notes": notes or "controlled debugging scenarios (one variable: model)",
        **environment_metadata(),
    }
    write_json_scrubbed(exp_dir / "metadata.json", metadata)

    sample_results = []
    try:
        with production_log_redirect(workspace):
            ctx = model_override(ROLE_DEBUGGER, effective_model) if debugger_model else _nullcontext()
            with ctx:
                for sample in debug_samples:
                    record = {
                        "sample": {
                            "sample_id": sample.sample_id,
                            "category": sample.category,
                            "buggy_failure_kind": sample.buggy_failure_kind,
                        },
                        "metrics": {},
                    }
                    metrics = measure_debug_repair(
                        sample, dataset_root(), workspace, max_iterations=max_iterations,
                    )
                    # Normalize for aggregation
                    metrics["repair_success_ratio"] = 1.0 if metrics["repair_success"] else 0.0
                    metrics["first_attempt_repair_ratio"] = 1.0 if metrics["first_attempt_repair"] else 0.0
                    metrics["regression_ratio"] = 1.0 if metrics["regression"] else 0.0
                    record["metrics"] = metrics
                    write_json_scrubbed(exp_dir / "samples" / f"{sample.sample_id}.json", record)
                    sample_results.append(record)
                    time.sleep(PAUSE_BETWEEN_LLM_CALLS)

        aggregated = aggregate_debugger_results(sample_results)
        aggregated["llm_calls"] = usage["calls"]
        aggregated["llm_prompt_tokens"] = usage["prompt"]
        aggregated["llm_completion_tokens"] = usage["completion"]
        write_aggregated(exp_dir, aggregated)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    return exp_dir


class _nullcontext:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False
