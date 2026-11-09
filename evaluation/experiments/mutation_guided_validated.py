"""
MG-v2: VALIDATED mutation-guided test generation (evaluation only).

Identical to mutation_guided (MG-v1) — same model/config/prompt/dataset/
mutation engine, same real surviving-mutant feedback — with ONE additional
variable: every generated additional test is INDIVIDUALLY validated against
the ORIGINAL, unmutated code before merging. A test is merged only if:

    1. it is syntactically valid (ast.parse),
    2. the merged suite executes successfully against the original source
       (the new test passes AND no previously passing test regresses),
    3. only test code is written (the sample source is never modified).

Rejection reasons are recorded per test. No simulation; every validation is
a real pytest run against the original source.
"""

import ast as pyast
import shutil
import time
import uuid
from pathlib import Path

from evaluation.config import (
    MAX_MUTANTS_PER_SAMPLE,
    TEMPERATURE,
    MAX_TOKENS,
    environment_metadata,
)
from evaluation.datasets.build import dataset_fingerprint
from evaluation.datasets.corpus import get_sample, writer_samples
from evaluation.experiments.mutation_guided import (
    _surviving_mutants,
    _targeted_user_prompt,
)
from evaluation.experiments.prompts import get_prompts
from evaluation.experiments.runner import evaluate_writer_sample
from evaluation.isolation import (
    cleanup_workspace,
    new_experiment_dir,
    new_workspace,
    production_log_redirect,
)
from evaluation.metrics.aggregate import write_aggregated
from evaluation.metrics.coverage import measure_coverage
from evaluation.metrics.execution import measure_execution
from evaluation.metrics.hallucination import measure_hallucination
from evaluation.metrics.mutation import (
    _suite_kills_prepared,
    generate_mutants,
    measure_mutation,
)
from evaluation.security import write_json_scrubbed


def _split_additional_tests(code: str) -> tuple[list[str], list[str]]:
    """
    Split generated additional code into individual top-level test-function
    snippets and helper statements. Returns (test_snippets, helpers).
    """
    try:
        tree = pyast.parse(code)
    except SyntaxError:
        return [], []
    lines = code.splitlines()
    tests, helpers = [], []
    for node in tree.body:
        start = node.lineno - 1
        if getattr(node, "decorator_list", None):
            start = min(d.lineno for d in node.decorator_list) - 1
        snippet = "\n".join(lines[start:node.end_lineno])
        if isinstance(node, (pyast.FunctionDef, pyast.AsyncFunctionDef)) and node.name.startswith("test_"):
            tests.append(snippet)
        else:
            helpers.append(snippet)
    return tests, helpers


def _validate_against_original(
    candidate_content: str,
    candidate_path: Path,
    source_dir: Path,
) -> tuple[bool, dict]:
    """
    Run the candidate merged suite against the ORIGINAL, unmutated source.
    Valid iff it parses, collects and every test passes (no regressions).
    """
    try:
        pyast.parse(candidate_content)
    except SyntaxError as e:
        return False, {"failed": 1, "errors": 1, "failed_test_names": [],
                       "stdout_excerpt": f"ast.parse failed: {e}"}
    execution = measure_execution(candidate_path, source_dir)
    ok = (
        execution["execution_success"]
        and execution["passed"] == execution["total_tests"]
        and execution["failed"] == 0
        and execution["errors"] == 0
    )
    return ok, execution


def _survivors_after(final_details: list[dict], survivors: list[dict]) -> list[dict]:
    """Survivors still alive after the final mutation run (kind==operator map)."""
    alive = []
    for m in survivors:
        killed_now = any(
            d["killed"] and d["line"] == m["line"] and d["kind"] == m["operator"]
            for d in final_details
        )
        if not killed_now:
            alive.append(m)
    return alive


def _evaluate_sample_v2(cfg, sample, workspace: Path, *prod) -> dict:
    (call_llm_with_retry, TokenTracker, validate_with_pytest_collect,
     build_correct_imports, strip_imports, inject_missing_imports,
     parse_llm_output, measure_execution, measure_mutation,
     measure_hallucination) = prod

    record = {
        "sample_id": sample.sample_id,
        "category": sample.category,
        "config": {
            "model": "production", "prompt_version": cfg["prompt_version"],
            "rag_enabled": False, "dataset_version": cfg["dataset_version"],
            "temperature": cfg["temperature"], "max_tokens": cfg["max_tokens"],
            "per_test_validation": True,
        },
        "baseline": {},
        "guided": {},
        "deltas": {},
        "ceiling_effect": False,
        "error": None,
    }

    # ── PHASE 1: baseline (identical to MG-v1) ────────────────────────────
    base_record = evaluate_writer_sample(cfg, sample, workspace)
    record["baseline"] = base_record

    exp_ws = workspace / sample.sample_id
    test_file = exp_ws / f"test_{Path(sample.entry_file).name}"
    source_dir = exp_ws / "source"

    baseline_m = base_record["metrics"]
    baseline_score = baseline_m.get("mutation_score")
    baseline_mutants_total = baseline_m.get("mutants_total") or 0

    if not test_file.exists() or not (source_dir / sample.entry_file).exists():
        record["error"] = f"baseline: {base_record.get('error') or 'artifacts missing'}"
        record["deltas"] = {"note": "baseline failed; guided phase skipped"}
        return record

    source = sample.files[sample.entry_file]
    survivors, total, score = _surviving_mutants(
        source, source_dir, sample.entry_file, test_file,
        sample.sample_id, cfg["max_mutants"],
    )
    if baseline_mutants_total and abs(score - (baseline_score or 0)) > 0.001:
        record["error"] = (f"mutation score mismatch between engine runs "
                           f"({score} vs {baseline_score})")
        return record

    record["baseline"]["surviving_mutants"] = survivors
    record["baseline"]["mutants_total"] = total
    record["baseline"]["mutants_killed"] = total - len(survivors)

    # ── Ceiling effect ─────────────────────────────────────────────────────
    if not survivors:
        record["ceiling_effect"] = True
        record["guided"] = {
            "note": "all mutants already killed — no guided step (no extra LLM call)",
            "additional_generated": 0, "additional_accepted": 0,
            "additional_rejected": 0,
            **{k: baseline_m.get(k) for k in (
                "pass_at_1", "execution_success", "line_coverage",
                "branch_coverage", "mutation_score", "mutants_total",
                "mutants_killed", "hallucination_rate", "latency_seconds",
                "llm_total_tokens")},
        }
        record["deltas"] = {k: 0 for k in (
            "mutation_score", "mutants_killed", "line_coverage",
            "branch_coverage", "pass_at_1")}
        return record

    # ── PHASE 2: guided generation (prompt IDENTICAL to MG-v1) ────────────
    system_prompt = get_prompts("P0")[0]()
    user_prompt = _targeted_user_prompt(sample, survivors)
    tracker = TokenTracker()
    t0 = time.perf_counter()
    additional, gen_error = call_llm_with_retry(
        system_prompt, user_prompt, f"mvalidated_{sample.sample_id}", tracker,
    )
    guided_llm_latency = round(time.perf_counter() - t0, 2)

    record["guided"] = {
        "survivors_given_to_llm": survivors,
        "additional_llm_tokens": tracker.total_tokens,
        "additional_llm_latency_seconds": guided_llm_latency,
        "additional_generated": 0,
        "additional_accepted": 0,
        "additional_rejected": 0,
        "accepted_tests": [],
        "rejected_tests": [],
    }
    if additional is None:
        record["error"] = f"guided generation failed: {gen_error}"
        record["deltas"] = {"note": "guided generation failed; baseline retained"}
        return record

    # ── PHASE 3: per-test validation against ORIGINAL code ────────────────
    cleaned = inject_missing_imports(strip_imports(additional))
    test_snippets, helper_snippets = _split_additional_tests(cleaned)
    helpers_block = "\n\n".join(helper_snippets)

    record["guided"]["additional_generated"] = len(test_snippets)

    merged_content = test_file.read_text(encoding="utf-8")
    if helper_snippets:
        merged_content = merged_content.rstrip() + "\n\n\n" + "\n\n".join(helper_snippets)

    for i, snippet in enumerate(test_snippets):
        test_name_guess = (pyast.parse(snippet).body[0].name
                           if _parses(snippet) else f"test_{i + 1}")
        candidate = merged_content.rstrip() + "\n\n\n" + snippet.lstrip() + "\n"
        candidate_path = exp_ws / f"_candidate_{i + 1}.py"
        candidate_path.write_text(candidate, encoding="utf-8")

        ok, execution = _validate_against_original(merged_content, candidate_path, source_dir)

        if ok:
            merged_content = candidate
            record["guided"]["accepted_tests"].append({
                "test_name": test_name_guess,
                "snippet": snippet,
            })
            record["guided"]["additional_accepted"] += 1
        else:
            failed_names = execution.get("failed_test_names", [])
            reason = "fails_against_original_code"
            record["guided"]["rejected_tests"].append({
                "test_name": test_name_guess,
                "snippet": snippet,
                "reason": reason,
                "failed_test_names": failed_names[:5],
            })
            record["guided"]["additional_rejected"] += 1

    # remove per-candidate scratch files; write the final merged suite
    for cand in exp_ws.glob("_candidate_*.py"):
        cand.unlink()
    test_file.write_text(merged_content, encoding="utf-8")
    record["guided"]["merged_accepted"] = record["guided"]["additional_accepted"] > 0

    # ── PHASE 4: final evaluation on the accepted merged suite ────────────
    execution = measure_execution(test_file, source_dir)
    record["guided"].update(execution)
    coverage = measure_coverage(test_file, source_dir, sample.entry_file)
    record["guided"].update({
        "line_coverage": coverage["line_coverage"],
        "branch_coverage": coverage["branch_coverage"],
    })
    mutation = measure_mutation(
        test_file, source_dir, sample.entry_file, max_mutants=cfg["max_mutants"],
    )
    record["guided"]["mutation_score"] = mutation["mutation_score"]
    record["guided"]["mutants_total"] = mutation["mutants_total"]
    record["guided"]["mutants_killed"] = mutation["mutants_killed"]
    record["guided"]["surviving_mutants_after"] = _survivors_after(
        mutation["mutant_details"], survivors)
    hall = measure_hallucination(merged_content, source_dir, sample.entry_file)
    record["guided"]["hallucination_rate"] = hall.get("hallucination_rate")

    # ── Deltas (guided - baseline) ─────────────────────────────────────────
    b, g = baseline_m, record["guided"]
    record["deltas"] = {
        "mutation_score": (g.get("mutation_score") or 0) - (baseline_score or 0),
        "mutants_killed": (g.get("mutants_killed") or 0) - (total - len(survivors)),
        "surviving_mutants": len(g.get("surviving_mutants_after", [])) - len(survivors),
        "line_coverage": (g.get("line_coverage") or 0) - (b.get("line_coverage") or 0),
        "branch_coverage": (g.get("branch_coverage") or 0) - (b.get("branch_coverage") or 0),
        "pass_at_1": (1.0 if g.get("pass_at_1") else 0.0) - (1.0 if b.get("pass_at_1") else 0.0),
        "tokens": (g.get("llm_total_tokens") or 0) + tracker.total_tokens
                  - (b.get("llm_total_tokens") or 0),
        "latency_seconds": round((g.get("latency_seconds") or 0)
                                 + guided_llm_latency - (b.get("latency_seconds") or 0), 2),
    }
    return record


def _parses(code: str) -> bool:
    try:
        pyast.parse(code)
        return True
    except SyntaxError:
        return False


def run_mutation_guided_validated(
    sample_ids: list[str] | None = None,
    max_mutants: int = MAX_MUTANTS_PER_SAMPLE,
    notes: str = "",
) -> Path:
    """MG-v2: validated mutation-guided generation (one variable vs MG-v1)."""
    from agents.test_writer import (
        build_correct_imports,
        call_llm_with_retry,
        inject_missing_imports,
        parse_llm_output,
        strip_imports,
        TokenTracker,
        validate_with_pytest_collect,
    )

    uid = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    exp_dir = new_experiment_dir("mutation_guided_validated", uid)
    workspace = new_workspace(uid)

    samples = [get_sample(sid) for sid in sample_ids] if sample_ids else writer_samples()

    cfg = {
        "prompt_version": "P0",
        "rag_enabled": False,
        "writer_model": None,
        "dataset_version": "v1",
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "mutation": True,
        "max_mutants": max_mutants,
    }

    metadata = {
        "experiment": "mutation_guided_validated",
        "experiment_id": exp_dir.name,
        "model": "production (see config.LLMConfig.TEST_WRITER_MODEL)",
        "prompt_version": "P0",
        "rag_enabled": False,
        "dataset_version": "v1",
        "dataset_hash": dataset_fingerprint(),
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "max_mutants": max_mutants,
        "per_test_validation": True,
        "validation_against": "original unmutated code",
        "sample_ids": [s.sample_id for s in samples],
        "notes": notes or "MG-v2: mutation feedback + per-test validation (only variable vs MG-v1)",
        **environment_metadata(),
    }
    write_json_scrubbed(exp_dir / "metadata.json", metadata)

    sample_results = []
    try:
        with production_log_redirect(workspace):
            for sample in samples:
                record = _evaluate_sample_v2(
                    cfg, sample, workspace,
                    call_llm_with_retry, TokenTracker, validate_with_pytest_collect,
                    build_correct_imports, strip_imports, inject_missing_imports,
                    parse_llm_output,
                    measure_execution,  # used by _validate_against_original
                    measure_mutation, measure_hallucination,
                )
                write_json_scrubbed(exp_dir / "samples" / f"{sample.sample_id}.json", record)
                sample_results.append(record)
    finally:
        cleanup_workspace(workspace)

    def _mean(key, items):
        vals = [s["deltas"].get(key) for s in items
                if isinstance(s.get("deltas"), dict) and s["deltas"].get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    ceilings = [s["sample_id"] for s in sample_results if s.get("ceiling_effect")]
    effective = [s for s in sample_results if not s.get("ceiling_effect")]

    aggregated = {
        "n_samples": len(sample_results),
        "n_ceiling_effect": len(ceilings),
        "ceiling_samples": ceilings,
        "n_effective": len(effective),
        "mutation_score_delta_mean": _mean("mutation_score", effective),
        "mutants_killed_delta_mean": _mean("mutants_killed", effective),
        "surviving_mutants_delta_mean": _mean("surviving_mutants", effective),
        "line_coverage_delta_mean": _mean("line_coverage", effective),
        "branch_coverage_delta_mean": _mean("branch_coverage", effective),
        "pass_at_1_delta_mean": _mean("pass_at_1", effective),
        "tokens_delta_mean": _mean("tokens", effective),
        "latency_delta_mean": _mean("latency_seconds", effective),
        "additional_generated_total": sum(s.get("guided", {}).get("additional_generated", 0)
                                          for s in sample_results),
        "additional_accepted_total": sum(s.get("guided", {}).get("additional_accepted", 0)
                                         for s in sample_results),
        "additional_rejected_total": sum(s.get("guided", {}).get("additional_rejected", 0)
                                         for s in sample_results),
        "rejection_reasons": {
            "fails_against_original_code": sum(
                1 for s in sample_results for r in s.get("guided", {}).get("rejected_tests", [])
                if r.get("reason") == "fails_against_original_code"),
        },
        "note": "MG-v2 = MG-v1 + per-test validation against original unmutated code",
    }
    write_aggregated(exp_dir, aggregated)
    return exp_dir
