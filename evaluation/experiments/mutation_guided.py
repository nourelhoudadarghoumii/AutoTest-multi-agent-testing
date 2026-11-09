"""
Mutation-guided test generation (OPTIMIZE stage — evaluation only).

Hypothesis: giving the Test Writer the REAL surviving mutants of its own
initial suite helps it generate additional tests that kill mutants the
initial suite missed.

Per sample:
    1. Baseline: generate tests normally (production P0 prompt, fixed model),
       execute, measure coverage, run the bounded mutation engine.
    2. If every mutant is already killed (or none exist) -> ceiling effect,
       record it, no guided step (no extra LLM call).
    3. Otherwise: extract the REAL surviving mutants (id, line, operator,
       original/mutated code — nothing else, no hidden/reference tests) and
       ask the model for ADDITIONAL targeted tests.
    4. Merge additional tests with the initial suite, validate, execute,
       measure coverage + mutation again.

Everything runs inside evaluation/ workspaces; production code is imported,
never modified.
"""

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
from evaluation.experiments.prompts import get_prompts
from evaluation.experiments.runner import evaluate_writer_sample
from evaluation.experiments.runner import (
    _analyse_sample,
    _build_functions_data,
    _select_functions,
)
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
from evaluation.metrics.mutation import measure_mutation
from evaluation.metrics.mutation import (
    MAX_MUTANTS_PER_SAMPLE,
    _suite_kills_prepared,
    generate_mutants,
)
from evaluation.security import write_json_scrubbed, contains_secret

import ast as pyast
import time as _time


# ── Survivor extraction (reuses the existing engine functions as-is) ─────

def _enclosing_function(source: str, lineno: int) -> str:
    """Name of the function containing the given 1-based line."""
    try:
        tree = pyast.parse(source)
    except SyntaxError:
        return "unknown"
    best = "module"
    for node in pyast.walk(tree):
        if isinstance(node, (pyast.FunctionDef, pyast.AsyncFunctionDef, pyast.ClassDef)):
            if node.lineno <= lineno <= (node.end_lineno or node.lineno):
                best = node.name
                if isinstance(node, (pyast.FunctionDef, pyast.AsyncFunctionDef)):
                    return best
    return best


def _changed_lines(original: str, mutated: str) -> tuple[str, str]:
    """First differing (original_line, mutated_line) pair."""
    orig_lines = original.splitlines()
    mut_lines = mutated.splitlines()
    for i in range(max(len(orig_lines), len(mut_lines))):
        o = orig_lines[i] if i < len(orig_lines) else "<removed>"
        m = mut_lines[i] if i < len(mut_lines) else "<added>"
        if o != m:
            return o.strip(), m.strip()
    return ("<identical>", "<identical>")


def _surviving_mutants(
    source: str,
    source_dir: Path,
    entry_rel: str,
    test_file: Path,
    sample_id: str,
    max_mutants: int,
    timeout: float = 60.0,
) -> tuple[list[dict], int]:
    """
    Run the existing bounded mutation engine (generate_mutants +
    _suite_kills_prepared — unchanged) and return only the REAL survivors
    with their original/mutated code, plus the total mutant count.
    """
    mutants = generate_mutants(source, max_mutants=max_mutants)
    if not mutants:
        return [], 0, None

    import tempfile

    survivors = []
    killed = 0
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        work_dir = Path(tmp) / "source"
        shutil.copytree(source_dir, work_dir)
        for idx, mut in enumerate(mutants):
            is_killed = _suite_kills_prepared(
                test_file, mut["source"], entry_rel, work_dir, timeout,
            )
            killed += int(is_killed)
            if not is_killed:
                original_line, mutated_line = _changed_lines(source, mut["source"])
                survivors.append({
                    "mutation_id": f"{sample_id}-M{idx:02d}",
                    "file": entry_rel,
                    "function": _enclosing_function(source, mut["line"]),
                    "line": mut["line"],
                    "operator": mut["kind"],
                    "original_code": original_line,
                    "mutated_code": mutated_line,
                })

    score = round(killed / len(mutants), 4)
    return survivors, len(mutants), score  # type: ignore[return-value]


def _targeted_user_prompt(sample, survivors: list[dict]) -> str:
    """User prompt containing ONLY the real surviving-mutant information and
    the source under test. Never exposes hidden/reference tests."""
    lines = [
        f"Target file: {sample.entry_file}",
        "",
        "The following mutants of this file SURVIVED the current test suite:",
        "",
    ]
    for s in survivors:
        lines.append(
            f"- Mutation {s['mutation_id']}: operator={s['operator']} at line "
            f"{s['line']} (function `{s['function']}`)\n"
            f"    original code: `{s['original_code']}`\n"
            f"    mutated code : `{s['mutated_code']}`"
        )
    lines.append("")
    lines.append("Source code under test:")
    lines.append("```python")
    lines.append(Path(sample.files[sample.entry_file]).read_text()
                 if False else sample.files[sample.entry_file])
    lines.append("```")
    lines.append("")
    lines.append(
        "Write ADDITIONAL pytest test functions that FAIL when any of these "
        "mutated versions is used instead of the original code (i.e. tests that "
        "kill each surviving mutant). Rules:\n"
        "- Only use the exact names defined in this source code.\n"
        "- Do NOT write import statements (they are added automatically).\n"
        "- Do NOT redefine the functions under test.\n"
        "- Every test must be complete, syntactically valid, and must pass "
        "against the ORIGINAL code.\n"
        "- Return the additional tests inside ONE <tests></tests> block, "
        "nothing else."
    )
    return "\n".join(lines)


# ── Experiment driver ─────────────────────────────────────────────────────

def run_mutation_guided_experiment(
    sample_ids: list[str] | None = None,
    max_mutants: int = MAX_MUTANTS_PER_SAMPLE,
    notes: str = "",
) -> Path:
    """Baseline (fresh generation) vs mutation-guided additional tests."""
    from agents.test_writer import (
        build_correct_imports,
        call_llm_with_retry,
        inject_missing_imports,
        parse_llm_output,
        strip_imports,
        validate_with_pytest_collect,
        TokenTracker,
    )
    uid = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    exp_dir = new_experiment_dir("mutation_guided", uid)
    workspace = new_workspace(uid)

    samples = [get_sample(sid) for sid in sample_ids] if sample_ids else writer_samples()

    cfg = {
        "prompt_version": "P0",
        "rag_enabled": False,
        "writer_model": None,  # production model
        "dataset_version": "v1",
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "mutation": True,
        "max_mutants": max_mutants,
    }

    metadata = {
        "experiment": "mutation_guided",
        "experiment_id": exp_dir.name,
        "model": "production (see config.LLMConfig.TEST_WRITER_MODEL)",
        "prompt_version": "P0",
        "rag_enabled": False,
        "dataset_version": "v1",
        "dataset_hash": dataset_fingerprint(),
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "max_mutants": max_mutants,
        "sample_ids": [s.sample_id for s in samples],
        "notes": notes or "baseline vs mutation-guided additional tests (one variable: survivor feedback)",
        **environment_metadata(),
    }
    write_json_scrubbed(exp_dir / "metadata.json", metadata)

    sample_results = []
    try:
        with production_log_redirect(workspace):
            for sample in samples:
                record = _evaluate_sample_guided(
                    cfg, sample, workspace, exp_dir,
                    call_llm_with_retry, TokenTracker,
                    validate_with_pytest_collect, build_correct_imports,
                    strip_imports, inject_missing_imports, parse_llm_output,
                    measure_execution, measure_coverage, measure_mutation,
                    measure_hallucination,
                )
                write_json_scrubbed(exp_dir / "samples" / f"{sample.sample_id}.json", record)
                sample_results.append(record)
    finally:
        cleanup_workspace(workspace)

    aggregated = _aggregate(sample_results)
    write_aggregated(exp_dir, aggregated)
    return exp_dir


def _evaluate_sample_guided(cfg, sample, workspace, exp_dir, *prod) -> dict:
    (call_llm_with_retry, TokenTracker, validate_with_pytest_collect,
     build_correct_imports, strip_imports, inject_missing_imports,
     parse_llm_output, measure_execution, measure_coverage, measure_mutation,
     measure_hallucination) = prod

    record = {
        "sample_id": sample.sample_id,
        "category": sample.category,
        "config": {
            "model": "production", "prompt_version": cfg["prompt_version"],
            "rag_enabled": False, "dataset_version": cfg["dataset_version"],
            "temperature": cfg["temperature"], "max_tokens": cfg["max_tokens"],
        },
        "baseline": {},
        "guided": {},
        "deltas": {},
        "ceiling_effect": False,
        "error": None,
    }

    # ── PHASE 1: baseline (normal generation) ─────────────────────────────
    base_record = evaluate_writer_sample(cfg, sample, workspace)
    record["baseline"] = base_record

    if base_record.get("error") and not base_record["metrics"].get("pass_at_1"):
        # generation failed entirely — no mutation data to guide on
        record["error"] = f"baseline: {base_record['error']}"
        record["deltas"] = {"note": "baseline failed; guided phase skipped"}
        return record

    # locate the baseline test file written by evaluate_writer_sample
    exp_ws = workspace / sample.sample_id
    test_file = exp_ws / f"test_{Path(sample.entry_file).name}"
    source_dir = exp_ws / "source"
    if not test_file.exists():
        record["error"] = "baseline test file missing"
        return record

    baseline_m = base_record["metrics"]
    baseline_mutants_total = baseline_m.get("mutants_total") or 0
    baseline_score = baseline_m.get("mutation_score")

    # ── Extract REAL surviving mutants (same engine, same semantics) ──────
    source = sample.files[sample.entry_file]
    survivors, total, score = _surviving_mutants(
        source, source_dir, sample.entry_file, test_file,
        sample.sample_id, cfg["max_mutants"],
    )
    # consistency check against measure_mutation's official result
    if baseline_mutants_total and abs(score - (baseline_score or 0)) > 0.001:
        record["error"] = (f"mutation score mismatch between engine runs "
                           f"({score} vs {baseline_score})")
        return record

    record["baseline"]["surviving_mutants"] = survivors
    record["baseline"]["mutants_total"] = total
    record["baseline"]["mutants_killed"] = total - len(survivors)

    # ── Ceiling effect: nothing to guide on ───────────────────────────────
    if not survivors:
        record["ceiling_effect"] = True
        record["guided"] = {
            "note": "all mutants already killed by the baseline suite — "
                    "no guided step performed (no additional LLM call)",
            **{k: baseline_m.get(k) for k in (
                "pass_at_1", "execution_success", "line_coverage",
                "branch_coverage", "mutation_score", "mutants_total",
                "mutants_killed", "hallucination_rate", "latency_seconds",
                "llm_total_tokens")},
            "additional_tests": 0,
            "additional_llm_tokens": 0,
            "additional_llm_latency_seconds": 0.0,
        }
        record["deltas"] = {k: 0 for k in (
            "mutation_score", "mutants_killed", "line_coverage",
            "branch_coverage", "pass_at_1")}
        return record

    # ── PHASE 2: mutation-guided additional tests ─────────────────────────
    system_prompt = get_prompts("P0")[0]()  # same production contract
    user_prompt = _targeted_user_prompt(sample, survivors)
    tracker = TokenTracker()
    t0 = _time.perf_counter()
    additional, gen_error = call_llm_with_retry(
        system_prompt, user_prompt, f"mguided_{sample.sample_id}", tracker,
    )
    guided_llm_latency = round(_time.perf_counter() - t0, 2)

    record["guided"] = {
        "survivors_given_to_llm": survivors,
        "additional_llm_tokens": tracker.total_tokens,
        "additional_llm_latency_seconds": guided_llm_latency,
        "additional_tests": 0,
    }
    if additional is None:
        record["error"] = f"guided generation failed: {gen_error}"
        record["deltas"] = {"note": "guided generation failed; baseline retained"}
        return record

    # ── Merge: append additional tests to the initial suite ───────────────
    initial_content = test_file.read_text(encoding="utf-8")
    cleaned_additional = inject_missing_imports(strip_imports(additional))
    merged = initial_content.rstrip() + "\n\n\n" + cleaned_additional.lstrip()

    try:
        pyast.parse(merged)
        merge_ast_ok = True
    except SyntaxError as e:
        record["error"] = f"merged suite failed ast.parse: {e}"
        record["guided"]["merged_accepted"] = False
        record["guided"]["additional_tests"] = 0
        return record
    record["guided"]["merged_accepted"] = merge_ast_ok

    # count additional test functions actually added
    def _count_tests(code):
        try:
            return sum(1 for n in pyast.walk(pyast.parse(code))
                       if isinstance(n, (pyast.FunctionDef, pyast.AsyncFunctionDef))
                       and n.name.startswith("test_"))
        except SyntaxError:
            return 0
    record["guided"]["additional_tests"] = max(
        0, _count_tests(merged) - _count_tests(initial_content))

    test_file.write_text(merged, encoding="utf-8")

    collect_ok = validate_with_pytest_collect(str(test_file), cwd=str(source_dir))
    record["guided"]["pytest_collect_passed"] = collect_ok

    # ── Re-execute + re-measure on the merged suite ───────────────────────
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
    # A survivor is considered killed now if a mutant at the same line with
    # the same operator was killed by the merged suite.
    still_surviving = []
    for m in survivors:
        killed_now = any(
            d["killed"] and d["line"] == m["line"] and d["kind"] == m["operator"]
            for d in mutation["mutant_details"]
        )
        if not killed_now:
            still_surviving.append(m)
    record["guided"]["surviving_mutants_after"] = still_surviving
    hall = measure_hallucination(merged, source_dir, sample.entry_file)
    record["guided"]["hallucination_rate"] = hall.get("hallucination_rate")

    # ── Deltas (guided - baseline) ────────────────────────────────────────
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


def _aggregate(sample_results: list[dict]) -> dict:
    """Aggregate deltas over non-ceiling, non-error samples."""
    def _mean(key, items):
        vals = [s["deltas"].get(key) for s in items
                if isinstance(s.get("deltas"), dict) and s["deltas"].get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    effective = [s for s in sample_results if not s.get("ceiling_effect")]
    ceilings = [s["sample_id"] for s in sample_results if s.get("ceiling_effect")]

    return {
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
        "additional_tests_total": sum(s.get("guided", {}).get("additional_tests", 0)
                                      for s in sample_results),
        "note": "deltas are guided minus baseline on the same initial generation",
    }
