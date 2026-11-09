"""Experiments package — fair-comparison experiment implementations."""

from evaluation.experiments.registry import (
    run_baseline,
    run_debugger_experiment,
    run_model_comparison,
    run_prompt_variants,
    run_rag_ab,
    run_retrieval_evaluation,
)

__all__ = [
    "run_baseline",
    "run_prompt_variants",
    "run_rag_ab",
    "run_model_comparison",
    "run_debugger_experiment",
    "run_retrieval_evaluation",
]
