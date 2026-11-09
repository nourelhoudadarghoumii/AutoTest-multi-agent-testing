"""
Debugger metrics: repair success, test recovery, first-attempt repair,
regression rate, iterations, latency, tokens.

Driven through the PRODUCTION debugger components (DebuggerLLM.diagnose_failure
+ apply_fix_safely) inside an isolated workspace, with re-execution via the
production pytest path.
"""

import re
import shutil
import time
from pathlib import Path

from agents.debugger import (
    DebuggerLLM,
    apply_fix_safely,
    extract_failure_info,
)
from agents.executor import run_tests_locally
from llm import DISABLE_REASONING


def _run_suite(test_file: Path, source_dir: Path) -> dict:
    results = run_tests_locally(
        test_files=[str(test_file)],
        source_files=[],
        base_dir=str(source_dir),
    )
    return {
        "total": results["total_tests"],
        "passed": results["passed"],
        "failed": results["failed"],
        "errors": results["errors"],
        "stdout": results["stdout"],
        "stderr": results["stderr"],
        "failed_test_names": list(results["failed_test_names"]),
    }


def _find_failing_test(stdout: str, failed_names: list[str]) -> str | None:
    """First failing test name, either from parsed names or the traceback."""
    if failed_names:
        return failed_names[0]
    match = re.search(r"_{3,}\s*(test_\w+)\s*_{3,}", stdout)
    return match.group(1) if match else None


def measure_debug_repair(
    sample,
    dataset_sample_dir: Path,
    workspace: Path,
    max_iterations: int = 3,
) -> dict:
    """
    Run the controlled debugging scenario for one sample:

        buggy test → execute → diagnose (production DebuggerLLM)
        → apply fix (production apply_fix_safely) → re-execute → …

    All inside `workspace` (isolated copy of source + buggy test).
    """
    from evaluation.config import DEBUGGER_TEMPERATURE, MAX_TOKENS

    # Materialize the isolated scenario
    scenario = workspace / sample.sample_id
    scenario.mkdir(parents=True, exist_ok=True)
    source_dir = scenario / "source"
    source_dir.mkdir()
    for rel, content in sample.files.items():
        (source_dir / rel).write_text(content, encoding="utf-8")
    buggy_file = scenario / "tests" / "test_buggy.py"
    buggy_file.parent.mkdir()
    buggy_file.write_text(sample.buggy_test, encoding="utf-8")

    before = _run_suite(buggy_file, source_dir)

    metrics = {
        "sample_id": sample.sample_id,
        "failure_kind": sample.buggy_failure_kind,
        "expected_repair": sample.expected_repair,
        "initial": {
            "total": before["total"], "passed": before["passed"],
            "failed": before["failed"],
        },
        "iterations": [],
        "iterations_used": 0,
        "final": None,
        "repair_success": False,
        "test_recovery_rate": 0.0,
        "first_attempt_repair": False,
        "regression": False,
        "latency_seconds": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "error": None,
    }

    initial_passed = before["passed"]
    total_tests = before["total"]

    try:
        debugger = DebuggerLLM()
    except Exception as exc:  # noqa: BLE001 — configuration failure
        metrics["error"] = f"debugger init failed: {exc}"
        return metrics

    start = time.perf_counter()
    current_state = before
    current_test = buggy_file

    for iteration in range(1, max_iterations + 1):
        if current_state["failed"] == 0 and current_state["errors"] == 0 and current_state["passed"] > 0:
            break  # everything green — done

        failing = _find_failing_test(current_state["stdout"], current_state["failed_test_names"])
        if failing is None:
            metrics["iterations"].append({
                "iteration": iteration, "note": "no failing test identified", "applied": False,
            })
            break

        failure = extract_failure_info(failing, str(current_test), current_state["stdout"], current_state["stderr"])
        if failure is None:
            metrics["iterations"].append({
                "iteration": iteration, "note": "failure info extraction failed", "applied": False,
            })
            break

        diagnosis = debugger.diagnose_failure(failure)

        iteration_record = {
            "iteration": iteration,
            "test_name": failing,
            "error_type": failure.error_type,
            "diagnosed": diagnosis is not None,
        }

        if diagnosis is not None:
            iteration_record["root_cause"] = diagnosis.root_cause[:300]
            iteration_record["confidence"] = diagnosis.confidence
            applied = apply_fix_safely(
                str(current_test), failing, diagnosis.fixed_code,
                test_dir=str(current_test.parent),
            )
            iteration_record["applied"] = applied

            if applied:
                current_state = _run_suite(current_test, source_dir)
        else:
            iteration_record["applied"] = False

        metrics["iterations"].append(iteration_record)
        metrics["iterations_used"] = iteration

        if iteration == 1 and iteration_record.get("applied") and current_state["failed"] == 0 and current_state["passed"] == total_tests:
            metrics["first_attempt_repair"] = True

    metrics["latency_seconds"] = round(time.perf_counter() - start, 2)

    after = _run_suite(current_test, source_dir)
    metrics["final"] = {
        "total": after["total"], "passed": after["passed"],
        "failed": after["failed"], "errors": after["errors"],
    }

    metrics["repair_success"] = (
        before["failed"] > 0 and after["failed"] == 0 and after["errors"] == 0
    )
    metrics["test_recovery_rate"] = round(
        after["passed"] / total_tests, 4
    ) if total_tests else 0.0
    metrics["regression"] = after["passed"] < initial_passed  # previously passing tests now fail

    # Cleanup scenario copy
    shutil.rmtree(scenario, ignore_errors=True)
    return metrics
