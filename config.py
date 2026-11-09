"""
Centralized Configuration for AutoTest
======================================

Professional configuration management with validation and type hints.
All model choices, parameters, and system settings in one place.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class PathConfig:
    """Path configuration for project structure."""

    ROOT_DIR = Path(__file__).parent
    WORKSPACE_DIR = ROOT_DIR / "workspace"
    LOGS_DIR = ROOT_DIR / "logs"
    CHROMA_DIR = ROOT_DIR / "chroma_data"

    # Ensure directories exist
    WORKSPACE_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    (LOGS_DIR / "executor").mkdir(exist_ok=True)
    (LOGS_DIR / "prompts").mkdir(exist_ok=True)
    (LOGS_DIR / "raw_llm").mkdir(exist_ok=True)


class LLMConfig:
    """LLM configuration — one FIXED free OpenRouter model per agent."""

    API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    # Fixed model per agent (no auto-selection, no fallbacks)
    TEST_WRITER_MODEL = (
        os.getenv("OPENROUTER_TEST_WRITER_MODEL", "").strip()
        or "cohere/north-mini-code:free"
    )
    DEBUGGER_MODEL = (
        os.getenv("OPENROUTER_DEBUGGER_MODEL", "").strip()
        or "nvidia/nemotron-3-super-120b-a12b:free"
    )

    # Generation parameters
    TEST_WRITER_TEMPERATURE = 0.3   # balanced diversity for test synthesis
    DEBUGGER_TEMPERATURE = 0.1      # deterministic repairs
    TIMEOUT = 90                    # seconds per call
    MAX_TOKENS = 2048

    @classmethod
    def is_configured(cls) -> bool:
        """True when an API key is present (placeholder values rejected)."""
        return bool(cls.API_KEY) and cls.API_KEY.strip() not in ("", "YOUR_KEY_HERE")

    @staticmethod
    def validate() -> list[str]:
        """Return a list of configuration problems (empty = OK)."""
        errors = []
        if not LLMConfig.is_configured():
            errors.append(
                "OPENROUTER_API_KEY not set in .env "
                "(get a key at https://openrouter.ai/keys)"
            )
        return errors


class ExecutionConfig:
    """Execution and runtime configuration."""

    # E2B Sandbox (optional — local fallback is used when absent)
    USE_E2B = os.getenv("E2B_API_KEY") is not None
    E2B_TIMEOUT = 300  # 5 minutes

    # Debugging loop guard — the debugger never runs more than this
    MAX_DEBUG_ITERATIONS = 3

    # API
    API_HOST = "0.0.0.0"
    API_PORT = 8000
    MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "100"))

    # Timeouts
    LLM_TIMEOUT = 120        # 2 minutes
    TEST_EXECUTION_TIMEOUT = 180  # 3 minutes


class LoggingConfig:
    """Logging configuration."""

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class RAGConfig:
    """RAG (Retrieval Augmented Generation) configuration."""

    COLLECTION_NAME = "bug_patterns"
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200
    TOP_K_RETRIEVAL = 3


class EvaluationConfig:
    """Quality score configuration (weights used by the Reporter)."""

    # Quality Score Weights
    WEIGHT_PASS_RATE = 0.40          # 40% — tests passing
    WEIGHT_COVERAGE = 0.30           # 30% — code coverage
    WEIGHT_COMPLEXITY = 0.20         # 20% — code complexity (inverse)
    WEIGHT_DEBUG_ITERATIONS = 0.10   # 10% — debug efficiency

    # Benchmarks
    BASELINE_QUALITY = 70    # acceptable threshold
    TARGET_QUALITY = 85      # target quality score for generated tests


# Export all configs
__all__ = [
    'PathConfig',
    'LLMConfig',
    'ExecutionConfig',
    'LoggingConfig',
    'RAGConfig',
    'EvaluationConfig',
]


if __name__ == "__main__":
    print("=" * 80)
    print("AutoTest Configuration")
    print("=" * 80)

    errors = LLMConfig.validate()
    if errors:
        for error in errors:
            print(f"❌ {error}")
    else:
        print("✅ Configuration valid")

    print("\nLLM (fixed models — no auto selection, no fallbacks):")
    print(f"  Provider    : OpenRouter ({LLMConfig.BASE_URL})")
    print(f"  Test Writer : {LLMConfig.TEST_WRITER_MODEL} (temperature {LLMConfig.TEST_WRITER_TEMPERATURE})")
    print(f"  Debugger    : {LLMConfig.DEBUGGER_MODEL} (temperature {LLMConfig.DEBUGGER_TEMPERATURE})")

    print("\nPaths:")
    print(f"  Workspace   : {PathConfig.WORKSPACE_DIR}")
    print(f"  Logs        : {PathConfig.LOGS_DIR}")

    print("\nExecution:")
    print(f"  E2B Sandbox : {'Enabled' if ExecutionConfig.USE_E2B else 'Disabled (local fallback)'}")
    print(f"  Max Debug   : {ExecutionConfig.MAX_DEBUG_ITERATIONS} iterations")

    print("\nEvaluation:")
    print(f"  Baseline    : {EvaluationConfig.BASELINE_QUALITY}")
    print(f"  Target      : {EvaluationConfig.TARGET_QUALITY}")

    print("=" * 80)
