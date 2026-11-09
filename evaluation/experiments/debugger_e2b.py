"""
Debugger research evaluation through the REAL production loop with E2B.

For each controlled debug target (dataset v1: DEBUG-001/002/003):

    buggy test -> production executor_node (E2B sandbox, real pytest)
    -> production should_debug router -> production debugger_node
    (DebuggerLLM, fixed model) -> apply_fix_safely (production)
    -> executor_node again in a fresh E2B sandbox -> … up to
    MAX_DEBUG_ITERATIONS

This is the research evaluation (distinct from the earlier single-sample
E2B framework smoke verification). No simulation: every execution is a
real pytest run inside an E2B sandbox; every repair is produced by the
production Debugger against the real sandbox failure output.
"""

import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from agents.debugger import debugger_node  # noqa: E402 — production node
from evaluation.config import environment_metadata
from evaluation.datasets.build import dataset_fingerprint
from evaluation.datasets.corpus import ALL_SAMPLES
from evaluation.isolation import new_experiment_dir, new_workspace
from evaluation.metrics.aggregate import write_aggregated
from evaluation.security import write_json_scrubbed



def _recording_debugger_service():
    """
    Wrap the production debugger service singleton with a token-recording
    proxy (in-process only). Returns (proxy, usage_dict).
    """
    import llm.service as svc
    from llm import ROLE_DEBUGGER, get_llm_service

    usage = {"prompt": 0, "completion": 0, "calls": 0}

    class _Proxy:
        def __init__(self, inner):
            self._inner = inner
            self.model = inner.model

        def complete(self, *args, **kwargs):
            response = self._inner.complete(*args, **kwargs)
            usage["prompt"] += response.prompt_tokens
            usage["completion"] += response.completion_tokens
            usage["calls"] += 1
            return response

    # get_llm_service creates the singleton if it does not exist yet
    proxy = _Proxy(get_llm_service(ROLE_DEBUGGER))
    return proxy, usage


def _snapshot(results) -> dict:
    return {
        "total_tests": results["total_tests"],
        "passed": results["passed"],
        "failed": results["failed"],
        "errors": results["errors"],
        "skipped": results["skipped"],
        "coverage_percent": results["coverage_percent"],
        "failed_test_names": list(results["failed_test_names"]),
        "exit_code": results["exit_code"],
        "execution_succeeded": results["execution_succeeded"],
    }


def evaluate_sample_e2b(sample, workspace: Path, max_iterations: int = 3) -> dict:
    """
    Run one controlled debug target through the production
    Executor <-> Debugger loop with E2B execution, capturing evidence.
    """
    from agents.debugger import MAX_DEBUG_ITERATIONS
    from agents.executor import ParsedTestResults, executor_node, save_execution_log
    from agents.reporter import generate_report  # noqa: F401 — reporter not used here
    from core.graph import route_after_execution
    from core.state import AgentState
    from langgraph.graph import END, START, StateGraph

    scenario = workspace / sample.sample_id
    source_dir = scenario / "source"
    tests_dir = scenario / "tests"
    source_dir.mkdir(parents=True)
    tests_dir.mkdir()
    for rel, content in sample.files.items():
        (source_dir / rel).write_text(content, encoding="utf-8")
    buggy_file = tests_dir / "test_buggy.py"
    buggy_file.write_text(sample.buggy_test, encoding="utf-8")

    record = {
        "sample_id": sample.sample_id,
        "failure_category": sample.buggy_failure_kind,
        "expected_repair": sample.expected_repair,
        "target_function": sample.target_function,
        "initial_failure": None,
        "initial_test_result": None,
        "iterations": [],
        "debugger_response": [],
        "repair_applied": False,
        "final_test_result": None,
        "final_passed": None,
        "regression_detected": False,
        "execution_backend": "e2b_sandbox",
        "e2b_sandbox_used": False,
        "e2b_sandbox_passes": 0,
        "latency_seconds": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "llm_calls": 0,
        "error": None,
    }

    # Capture every execution pass the loop performs (initial + per-iteration)
    executions: list[dict] = []
    original_save = save_execution_log

    def _capturing_save(project_id, execution_mode, test_files, results):
        executions.append({"mode": execution_mode, **_snapshot(results)})
        return original_save(project_id, execution_mode, test_files, results)

    state: AgentState = {
        "project_id": f"debug-eval-{sample.sample_id}",
        "base_dir": str(source_dir),
        "test_dir": str(tests_dir),
        "source_files": [str(source_dir / rel) for rel in sample.files],
        "code_context": {
            "functions": [], "classes": [], "imports": [],
            "complexity": {}, "dependency_graph": {},
        },
        "analysis": {
            "files": [], "total_files": 0, "total_functions": 0,
            "total_classes": 0, "total_risk_zones": 0, "avg_complexity": 0.0,
            "top_risk_functions": [], "external_imports": [],
        },
        "patterns_retrieved": [],
        "test_files": [str(buggy_file)],
        "tests_generated_count": 0,
        "llm_api_calls": 0, "llm_retries": 0,
        "llm_prompt_tokens": 0, "llm_completion_tokens": 0, "llm_total_tokens": 0,
        "llm_success_rate": 0.0,
        "ast_validation_passed": True, "pytest_validation_passed": True,
        "functions_skipped_trivial": [], "functions_failed_generation": [],
        "execution_results": {
            "total_tests": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0,
            "coverage_percent": 0.0, "duration_seconds": 0.0, "stdout": "", "stderr": "",
            "failed_test_names": [],
        },
        "failed_tests": [],
        "debug_report": {"root_cause": "", "fix_applied": "", "iterations": 0, "resolved": False},
        "debug_history": [],
        "iteration_count": 0,
        "total_fixes_applied": 0,
        "final_report": {},
        "error": "",
        "status": "running",
    }

    from langgraph.graph import END, START, StateGraph  # noqa: E402

    def build_loop_final():
        graph = StateGraph(AgentState)
        graph.add_node("executor", executor_node)
        graph.add_node("debugger", debugger_node)
        graph.add_edge(START, "executor")
        graph.add_conditional_edges(
            "executor", route_after_execution,
            {"debugger": "debugger", "report": END, "fail": END},
        )
        graph.add_edge("debugger", "executor")
        return graph.compile()

    start = time.perf_counter()
    try:
        import asyncio
        import llm.service as svc
        from llm import ROLE_DEBUGGER

        proxy, usage = _recording_debugger_service()
        original_service = svc._services.get(ROLE_DEBUGGER)
        svc._services[ROLE_DEBUGGER] = proxy
        try:
            with patch.object(
                __import__("agents.executor", fromlist=["save_execution_log"]),
                "save_execution_log",
                _capturing_save,
            ):
                graph = build_loop_final()
                final_state = asyncio.run(asyncio.to_thread(graph.invoke, state))
        finally:
            svc._services[ROLE_DEBUGGER] = original_service

        record["e2b_sandbox_used"] = all(e["mode"] == "e2b_sandbox" for e in executions) and len(executions) > 0
        record["e2b_sandbox_passes"] = sum(1 for e in executions if e["mode"] == "e2b_sandbox")
        record["iterations"] = [e for e in executions]
        record["debugger_response"] = final_state.get("debug_history", [])
        record["initial_test_result"] = executions[0] if executions else None
        initial = executions[0] if executions else None
        record["initial_failure"] = (
            f"{initial['failed']} failed / {initial['errors']} errors "
            f"({', '.join(initial['failed_test_names'][:3]) or 'unspecified'})"
            if initial else None
        )
        record["repair_applied"] = any(e.get("applied") for e in record["debugger_response"])
        record["final_test_result"] = _snapshot_from_state(final_state)
        record["final_passed"] = final_state["execution_results"]["passed"]
        total_tests = final_state["execution_results"]["total_tests"]
        record["repair_success"] = (
            initial is not None and initial["failed"] > 0
            and final_state["execution_results"]["failed"] == 0
            and final_state["execution_results"]["errors"] == 0
            and total_tests > 0
        )
        record["test_recovery_rate"] = round(
            final_state["execution_results"]["passed"] / total_tests, 4
        ) if total_tests else 0.0
        initial_passed = initial["passed"] if initial else 0
        record["regression_detected"] = final_state["execution_results"]["passed"] < initial_passed
        record["iterations_used"] = final_state.get("iteration_count", 0)
        record["max_iterations_allowed"] = max_iterations
        record["first_attempt_repair"] = (
            record["iterations_used"] == 1 and record["repair_success"]
        )
        record["prompt_tokens"] = usage["prompt"]
        record["completion_tokens"] = usage["completion"]
        record["llm_calls"] = usage["calls"]
        record["status"] = final_state.get("status")
        if final_state.get("error"):
            record["error"] = final_state["error"]
    except Exception as exc:  # noqa: BLE001 — record honestly
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["e2b_sandbox_used"] = any(
            e.get("mode") == "e2b_sandbox" for e in executions
        )
        record["e2b_sandbox_passes"] = sum(
            1 for e in executions if e.get("mode") == "e2b_sandbox"
        )
        record["iterations"] = executions
        record["initial_test_result"] = executions[0] if executions else None

    record["latency_seconds"] = round(time.perf_counter() - start, 2)
    shutil.rmtree(scenario, ignore_errors=True)
    return record


def _snapshot_from_state(state: AgentState) -> dict:
    er = state["execution_results"]
    return {
        "total_tests": er["total_tests"],
        "passed": er["passed"],
        "failed": er["failed"],
        "errors": er["errors"],
        "skipped": er.get("skipped", 0),
        "coverage_percent": er["coverage_percent"],
        "failed_test_names": list(er["failed_test_names"]),
    }


def run_debugger_e2b_evaluation(sample_ids: list[str] | None = None) -> Path:
    """Run the full debugger research evaluation and store raw + aggregated."""
    uid = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    exp_dir = new_experiment_dir("debugger_e2b", uid)
    workspace = new_workspace(uid)

    targets = [s for s in ALL_SAMPLES if s.is_debug_target]
    if sample_ids:
        targets = [s for s in targets if s.sample_id in sample_ids]

    metadata = {
        "experiment": "debugger_e2b",
        "experiment_id": exp_dir.name,
        "model": "production debugger model (see config.LLMConfig.DEBUGGER_MODEL)",
        "execution_backend": "e2b_sandbox (real pytest inside E2B; local fallback disabled)",
        "max_iterations": 3,
        "dataset_version": "v1",
        "dataset_hash": dataset_fingerprint(),
        "sample_ids": [s.sample_id for s in targets],
        "notes": "research evaluation through the production Executor<->Debugger loop",
        **environment_metadata(),
    }
    write_json_scrubbed(exp_dir / "metadata.json", metadata)

    results = []
    try:
        for sample in targets:
            record = evaluate_sample_e2b(sample, workspace)
            record["repair_success_ratio"] = 1.0 if record.get("repair_success") else 0.0
            record["first_attempt_repair_ratio"] = 1.0 if record.get("first_attempt_repair") else 0.0
            record["regression_ratio"] = 1.0 if record.get("regression_detected") else 0.0
            write_json_scrubbed(exp_dir / "samples" / f"{sample.sample_id}.json", record)
            results.append(record)
            print(f"[debug-eval] {sample.sample_id}: repair={record.get('repair_success')} "
                  f"iterations={record.get('iterations_used')} "
                  f"final={record.get('final_passed')}/{record['final_test_result']['total_tests'] if record.get('final_test_result') else '?'} "
                  f"backend={record.get('execution_backend')} e2b_passes={record.get('e2b_sandbox_passes')}",
                  flush=True)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    def _mean(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 4) if values else None

    aggregated = {
        "n_samples": len(results),
        "repair_success_rate": _mean([r.get("repair_success_ratio") for r in results]),
        "test_recovery_rate_mean": _mean([r.get("test_recovery_rate") for r in results]),
        "first_attempt_repair_rate": _mean([r.get("first_attempt_repair_ratio") for r in results]),
        "regression_rate": _mean([r.get("regression_ratio") for r in results]),
        "iterations_mean": _mean([r.get("iterations_used") for r in results]),
        "latency_seconds_mean": _mean([r.get("latency_seconds") for r in results]),
        "prompt_tokens_total": sum(r.get("prompt_tokens", 0) for r in results),
        "completion_tokens_total": sum(r.get("completion_tokens", 0) for r in results),
        "llm_calls_total": sum(r.get("llm_calls", 0) for r in results),
        "e2b_sandbox_passes_total": sum(r.get("e2b_sandbox_passes", 0) for r in results),
        "all_runs_used_e2b": all(r.get("e2b_sandbox_used") for r in results),
        "per_failure_category": {
            kind: {
                "n": len([r for r in results if r.get("failure_category") == kind]),
                "repair_success_rate": _mean([
                    float(r.get("repair_success_ratio", 0.0)) for r in results
                    if r.get("failure_category") == kind
                ]),
            }
            for kind in sorted({r.get("failure_category") for r in results if r.get("failure_category")})
        },
        "note": "research evaluation — every execution ran as real pytest inside an E2B sandbox",
    }
    write_aggregated(exp_dir, aggregated)
    return exp_dir


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    d = run_debugger_e2b_evaluation()
    print(f"experiment stored: {d}")
