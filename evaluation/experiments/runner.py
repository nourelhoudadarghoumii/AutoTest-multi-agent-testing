"""
Fair-comparison experiment runner.

Invariants (enforced here, once):
    - ONE variable changes per experiment; everything else is identical.
    - Identical dataset version, temperature, max_tokens, timeout, caps.
    - All writes stay under evaluation/ (isolation guard).
    - Production prompt P0 is imported from agents.test_writer (never copied).
    - Production log writers are redirected to the experiment workspace.
    - Every result record passes the secret scrubber before hitting disk.

Experiment flow per Test Writer sample (production leaf logic reused):
    analyser_node (reuse) → select functions → build user prompt (reuse
    production builder for P0 / structured builder for P1+) → LLM via the
    production service (role-bound, optional in-process model override) →
    parse_llm_output (reuse) → post-process (reuse) → validate (reuse) →
    execute via production run_tests_locally (reuse) → measure coverage /
    mutation / hallucination / text-similarity.
"""

import shutil
import time
import uuid
from pathlib import Path

from evaluation.config import (
    MAX_TOKENS,
    PAUSE_BETWEEN_LLM_CALLS,
    TEMPERATURE,
    environment_metadata,
)
from evaluation.datasets.build import dataset_root, dataset_fingerprint
from evaluation.datasets.corpus import get_sample, writer_samples
from evaluation.experiments.prompts import get_prompts, uses_rag
from evaluation.isolation import (
    cleanup_workspace,
    new_experiment_dir,
    new_workspace,
    production_log_redirect,
)
from evaluation.metrics.aggregate import (
    aggregate_writer_results,
    write_aggregated,
)
from evaluation.metrics.coverage import measure_coverage
from evaluation.metrics.execution import measure_execution
from evaluation.metrics.hallucination import measure_hallucination
from evaluation.metrics.mutation import measure_mutation
from evaluation.metrics.textsim import measure_text_similarity
from evaluation.security import write_json_scrubbed, contains_secret

import ast as pyast


# ── Orchestration helpers (leaf logic imported from production) ───────────

def _analyse_sample(source_dir: Path, entry_file: str, files: dict[str, str]) -> dict:
    """Run the production analyser node on this sample (reused, unmodified)."""
    from agents.analyser import analyser_node
    from core.state import AgentState

    source_files = [str(source_dir / rel) for rel in files]
    state: AgentState = {
        "project_id": "eval",
        "base_dir": str(source_dir),
        "test_dir": str(source_dir / "_tests"),
        "source_files": source_files,
        "code_context": {"functions": [], "classes": [], "imports": [],
                         "complexity": {}, "dependency_graph": {}},
        "patterns_retrieved": [],
        "test_files": [],
        "tests_generated_count": 0,
        "llm_api_calls": 0, "llm_retries": 0,
        "llm_prompt_tokens": 0, "llm_completion_tokens": 0, "llm_total_tokens": 0,
        "llm_success_rate": 0.0,
        "ast_validation_passed": False, "pytest_validation_passed": False,
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
    state["analysis"] = {"files": [], "total_files": 0, "total_functions": 0,
                         "total_classes": 0, "total_risk_zones": 0, "avg_complexity": 0.0,
                         "top_risk_functions": [], "external_imports": []}
    return analyser_node(state)


def _select_functions(state: dict, entry_file: str) -> tuple[list[dict], list[str]]:
    """Pick target functions for the entry file (mirrors test_writer_node's
    selection using the production should_test_function)."""
    from agents.test_writer import should_test_function

    complexity = state["code_context"]["complexity"]
    risk_zones = [name.split("::")[-1] for name, score in complexity.items() if score > 5]

    file_funcs = []
    for func in state["code_context"]["functions"]:
        name = func["name"]
        if any(k.startswith(f"{entry_file}::") and (k.endswith(f"::{name}") or k.endswith(f".{name}"))
               for k in complexity):
            file_funcs.append(func)

    targeted = []
    for func in file_funcs:
        if should_test_function(func, risk_zones):
            targeted.append(func)
    return targeted, risk_zones


def _build_functions_data(state: dict, source_dir: Path, entry_file: str,
                          targeted: list[dict], risk_zones: list[str],
                          rag_memory=None) -> list[dict]:
    """Assemble per-function data (mirrors test_writer_node's aggregation;
    reuses production source-extraction helpers and RAG formatting)."""
    from agents.test_writer import (
        get_class_init_source,
        get_function_source,
        retrieve_rag_patterns,
    )

    complexity = state["code_context"]["complexity"]
    try:
        tree = pyast.parse((source_dir / entry_file).read_text(encoding="utf-8"))
        available_names = [n.name for n in tree.body
                           if isinstance(n, (pyast.FunctionDef, pyast.AsyncFunctionDef, pyast.ClassDef))]
        method_to_class = {
            item.name: node.name
            for node in tree.body if isinstance(node, pyast.ClassDef)
            for item in node.body if isinstance(item, (pyast.FunctionDef, pyast.AsyncFunctionDef))
        }
    except SyntaxError:
        available_names, method_to_class = [], {}

    functions_data = []
    for func in targeted:
        name = func["name"]
        score = 0.0
        for key, value in complexity.items():
            if key.startswith(f"{entry_file}::") and (key.endswith(f"::{name}") or key.endswith(f".{name}")):
                score = float(value)
                break

        decorators = []
        if func.get("decorators"):
            import json
            try:
                decorators = json.loads(func["decorators"])
            except Exception:  # noqa: BLE001
                pass

        class_name = method_to_class.get(name, "")
        rag_section = ""
        if rag_memory is not None:
            retrieved = rag_memory.retrieve_similar_patterns(
                function_name=name,
                function_signature=f"{name}({func.get('args', '')})",
                complexity=score,
                n_results=3,
            )
            rag_section = retrieve_rag_patterns(name, score, retrieved)

        functions_data.append({
            "name": name,
            "signature": f"{name}({func.get('args', '')})",
            "return_type": func.get("return_type", "Any"),
            "docstring": func.get("docstring", ""),
            "complexity_score": score,
            "is_risk_zone": name in risk_zones,
            "decorators": decorators,
            "is_async": func.get("is_async") == "True",
            "rag_section": rag_section,
            "function_source_code": get_function_source(str(source_dir / entry_file), name),
            "class_name": class_name,
            "init_source": get_class_init_source(str(source_dir / entry_file), class_name) if class_name else "",
        })
    return functions_data, available_names


# ── Per-sample writer evaluation ──────────────────────────────────────────

def evaluate_writer_sample(cfg: dict, sample, workspace: Path, rag_memory=None) -> dict:
    """Full pipeline for one sample under `cfg` (one variable changed)."""
    from agents.test_writer import (
        build_correct_imports,
        call_llm_with_retry,
        inject_missing_imports,
        parse_llm_output,
        post_process_test_content,
        strip_imports,
        validate_with_pytest_collect,
        TokenTracker,
    )
    from llm import get_llm_service, ROLE_TEST_WRITER
    from agents.executor import parse_pytest_output
    import subprocess
    import sys as _sys
    import json as _json

    record = {
        "sample": {
            "sample_id": sample.sample_id, "category": sample.category,
            "difficulty": sample.difficulty, "entry_file": sample.entry_file,
            "tags": list(sample.tags),
        },
        "config": {
            "model": cfg.get("writer_model") or "production",
            "prompt_version": cfg["prompt_version"],
            "rag_enabled": cfg["rag_enabled"],
            "dataset_version": cfg["dataset_version"],
            "temperature": cfg["temperature"],
            "max_tokens": cfg["max_tokens"],
        },
        "metrics": {},
        "artifacts": {},
        "error": None,
    }

    # Workspace: source copy
    exp_ws = workspace / sample.sample_id
    source_dir = exp_ws / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in sample.files.items():
        (source_dir / rel).write_text(content, encoding="utf-8")

    try:
        # 1. Analysis (production analyser, reused)
        state = _analyse_sample(source_dir, sample.entry_file, sample.files)
        targeted, risk_zones = _select_functions(state, sample.entry_file)
        if not targeted:
            record["error"] = "no testable functions selected"
            return record

        rag_memory_for_prompt = rag_memory if (cfg["rag_enabled"] and uses_rag(cfg["prompt_version"])) else None
        functions_data, available_names = _build_functions_data(
            state, source_dir, sample.entry_file, targeted, risk_zones, rag_memory_for_prompt)

        # 2. Prompt (P0 imports production; P1–P3 structured variants)
        system_fn, user_fn = get_prompts(cfg["prompt_version"])
        system_prompt = system_fn()
        user_prompt = user_fn(sample.entry_file, functions_data, available_names)

        # 3. LLM call through the PRODUCTION service (reuse call_llm_with_retry:
        #    bounded generation attempts + rate-limit handling + DISABLE_REASONING)
        tracker = TokenTracker()
        start = time.perf_counter()
        result, error_reason = call_llm_with_retry(
            system_prompt, user_prompt, f"eval_{sample.sample_id}", tracker,
        )
        llm_latency = round(time.perf_counter() - start, 2)

        record["metrics"]["llm_latency_seconds"] = llm_latency
        record["metrics"]["llm_api_calls"] = tracker.total_calls
        record["metrics"]["llm_retries"] = tracker.total_retries
        record["metrics"]["llm_prompt_tokens"] = tracker.total_prompt_tokens
        record["metrics"]["llm_completion_tokens"] = tracker.total_completion_tokens
        record["metrics"]["llm_total_tokens"] = tracker.total_tokens

        if result is None:
            record["error"] = f"generation failed: {error_reason}"
            record["metrics"]["pass_at_1"] = 0.0
            record["metrics"]["execution_success"] = 0.0
            record["metrics"]["line_coverage"] = 0.0
            record["metrics"]["branch_coverage"] = 0.0
            return record

        # 4. Post-process with production logic (reused)
        header = build_correct_imports(str(source_dir / sample.entry_file), str(exp_ws))
        content = inject_missing_imports(header + strip_imports(result))
        content = post_process_test_content(
            content=content,
            source_file_path=str(source_dir / sample.entry_file),
            test_dir=str(exp_ws),
        )
        test_file = exp_ws / f"test_{Path(sample.entry_file).name}"
        test_file.write_text(content, encoding="utf-8")
        record["artifacts"]["test_file"] = str(test_file.relative_to(workspace))

        # 5. Validation (production validators, reused)
        try:
            pyast.parse(test_file.read_text(encoding="utf-8"))
            ast_ok = True
        except SyntaxError:
            ast_ok = False
        collect_ok = validate_with_pytest_collect(str(test_file), cwd=str(source_dir))
        record["metrics"]["ast_validation_passed"] = ast_ok
        record["metrics"]["pytest_collect_passed"] = collect_ok

        # 6. Execution (production executor, reused)
        execution = measure_execution(test_file, source_dir)
        record["metrics"].update(execution)

        # 7. Coverage (line + branch)
        coverage = measure_coverage(test_file, source_dir, sample.entry_file)
        record["metrics"].update({
            "line_coverage": coverage["line_coverage"],
            "branch_coverage": coverage["branch_coverage"],
        })

        # 8. Mutation (optional)
        if cfg.get("mutation", False):
            record["metrics"].update(measure_mutation(
                test_file, source_dir, sample.entry_file,
                max_mutants=cfg.get("max_mutants", 8),
            ))
        else:
            record["metrics"]["mutation_score"] = None

        # 9. Hallucination
        record["metrics"].update(measure_hallucination(content, source_dir, sample.entry_file))

        # 10. Text similarity vs reference (similarity only)
        if sample.reference_test is not None:
            record["metrics"].update(measure_text_similarity(content, sample.reference_test))

        time.sleep(PAUSE_BETWEEN_LLM_CALLS)

    except Exception as exc:  # noqa: BLE001 — record and continue
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["metrics"].setdefault("pass_at_1", 0.0)
        record["metrics"].setdefault("execution_success", 0.0)
        record["metrics"].setdefault("line_coverage", 0.0)
        record["metrics"].setdefault("branch_coverage", 0.0)

    return record


# ── Experiment driver ─────────────────────────────────────────────────────

def run_writer_experiment(
    name: str,
    prompt_version: str = "P0",
    rag_enabled: bool = False,
    rag_memory=None,
    writer_model: str | None = None,
    mutation: bool = False,
    max_mutants: int = 8,
    sample_ids: list[str] | None = None,
    notes: str = "",
) -> Path:
    """
    Run one Test Writer experiment and store raw + aggregated results.

    Only `prompt_version`, `rag_enabled` and `writer_model` differ between
    runs; everything else is fixed here (fair comparison).
    """
    from llm import get_llm_service, ROLE_TEST_WRITER

    uid = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    exp_dir = new_experiment_dir(name, uid)
    workspace = new_workspace(uid)

    production = get_llm_service(ROLE_TEST_WRITER)
    effective_model = writer_model or production.model

    cfg = {
        "prompt_version": prompt_version,
        "rag_enabled": rag_enabled,
        "writer_model": effective_model,
        "dataset_version": "v1",
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "mutation": mutation,
        "max_mutants": max_mutants,
    }

    samples = [get_sample(sid) for sid in sample_ids] if sample_ids else writer_samples()

    metadata = {
        "experiment": name,
        "experiment_id": exp_dir.name,
        "prompt_version": prompt_version,
        "rag_enabled": rag_enabled,
        "rag_store": "isolated_seeded" if rag_enabled else "off",
        "model": effective_model,
        "model_overridden": writer_model is not None,
        "dataset_version": "v1",
        "dataset_hash": dataset_fingerprint(),
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "mutation": mutation,
        "max_mutants": max_mutants,
        "sample_ids": [s.sample_id for s in samples],
        "notes": notes,
        **environment_metadata(),
    }
    write_json_scrubbed(exp_dir / "metadata.json", metadata)

    sample_results = []
    try:
        with production_log_redirect(workspace):
            if writer_model:
                from evaluation.isolation import model_override
                with model_override(ROLE_TEST_WRITER, writer_model):
                    for sample in samples:
                        record = evaluate_writer_sample(cfg, sample, workspace, rag_memory)
                        write_json_scrubbed(exp_dir / "samples" / f"{sample.sample_id}.json", record)
                        sample_results.append(record)
            else:
                for sample in samples:
                    record = evaluate_writer_sample(cfg, sample, workspace, rag_memory)
                    write_json_scrubbed(exp_dir / "samples" / f"{sample.sample_id}.json", record)
                    sample_results.append(record)
    finally:
        cleanup_workspace(workspace)

    aggregated = aggregate_writer_results(sample_results)
    write_aggregated(exp_dir, aggregated)
    return exp_dir
