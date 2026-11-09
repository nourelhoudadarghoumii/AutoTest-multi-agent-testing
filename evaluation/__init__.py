"""
AutoTest Evaluation Layer
=========================

An isolated GenAI experimentation layer around the AutoTest pipeline.

Methodology: SCOPE → SELECT → ADAPT & ALIGN → EVALUATE → OPTIMIZE

This package NEVER modifies production behavior. It imports production
components (agents.*, llm.*, utils.rag, core.state) read-only and runs all
experiments inside isolated workspaces under evaluation/.
"""

from evaluation.config import (
    DATASET_VERSION,
    EVAL_ROOT,
    RESULTS_DIR,
    REPORTS_DIR,
    DATASETS_DIR,
)

__version__ = "1.0.0"

__all__ = [
    "DATASET_VERSION",
    "EVAL_ROOT",
    "RESULTS_DIR",
    "REPORTS_DIR",
    "DATASETS_DIR",
]
