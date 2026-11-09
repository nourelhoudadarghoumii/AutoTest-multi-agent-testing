"""
Execution metrics: does the generated test suite run, and does it pass?

Reuses the production executor (run_tests_locally + parse_pytest_output)
so evaluation measures exactly what production measures.
"""

import time
from pathlib import Path

from agents.executor import run_tests_locally


def measure_execution(
    test_file: Path,
    source_dir: Path,
    timeout_seconds: float = 120.0,
) -> dict:
    """
    Run one generated test file against its source directory.

    Returns execution success, pass@1 (all tests passing on the first and
    only execution), counts, and wall-clock latency.
    """
    start = time.perf_counter()
    results = run_tests_locally(
        test_files=[str(test_file)],
        source_files=[],
        base_dir=str(source_dir),
    )
    latency = round(time.perf_counter() - start, 2)

    total = results["total_tests"]
    passed = results["passed"]

    return {
        "execution_success": total > 0,          # suite collected AND ran
        "pass_at_1": total > 0 and passed == total and results["failed"] == 0 and results["errors"] == 0,
        "total_tests": total,
        "passed": passed,
        "failed": results["failed"],
        "errors": results["errors"],
        "skipped": results["skipped"],
        "failed_test_names": results["failed_test_names"][:10],
        "stdout_excerpt": results["stdout"][-2000:],
        "latency_seconds": latency,
    }
