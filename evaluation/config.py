"""
Evaluation-layer configuration.

Reads production configuration read-only (LLMConfig) — never mutates it.
Defines evaluation-specific constants: paths, caps, defaults.
"""

import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────
EVAL_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_ROOT / "results"
REPORTS_DIR = EVAL_ROOT / "reports"
DATASETS_DIR = EVAL_ROOT / "datasets"
GENERATED_DATASETS_DIR = DATASETS_DIR / "generated"
DATASET_VERSION = "v1"

# Make production modules importable when running `python -m evaluation.*`
PROJECT_ROOT = EVAL_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Fair-comparison defaults (mirror production generation parameters) ───
TEMPERATURE = 0.3          # production Test Writer temperature
DEBUGGER_TEMPERATURE = 0.1  # production Debugger temperature
MAX_TOKENS = 2048           # production max_tokens (post-fix)
LLM_TIMEOUT = 90.0          # seconds per call, same as production

# ── Experiment caps (free-tier friendly, bounded runtime) ────────────────
MAX_MUTANTS_PER_SAMPLE = 8   # AST mutation budget per sample
SMOKE_SAMPLES = 2            # smoke test sample count
SMOKE_MUTATION = False       # mutation OFF in smoke (runtime)
PAUSE_BETWEEN_LLM_CALLS = 2.0  # seconds — stay under the 20 req/min free limit

# ── Ground truth for retrieval evaluation ─────────────────────────────────
RETRIEVAL_K = 3              # matches production retrieve_similar_patterns(n_results=3)


def production_models() -> dict:
    """Read the current production model configuration (read-only)."""
    from config import LLMConfig

    return {
        "test_writer_model": LLMConfig.TEST_WRITER_MODEL,
        "debugger_model": LLMConfig.DEBUGGER_MODEL,
        "base_url": LLMConfig.BASE_URL,
        "temperature": LLMConfig.TEST_WRITER_TEMPERATURE,
        "debugger_temperature": LLMConfig.DEBUGGER_TEMPERATURE,
        "max_tokens": LLMConfig.MAX_TOKENS,
    }


def environment_metadata() -> dict:
    """Reproducibility metadata recorded with every experiment."""
    import platform
    import datetime

    return {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "dataset_version": DATASET_VERSION,
    }
