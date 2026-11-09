"""
Aggregation: per-sample results -> aggregated.json + comparison tables.

Never overwrites: every experiment writes to its own append-only directory.
"""

import statistics
from pathlib import Path

from evaluation.security import write_json_scrubbed


def _safe_mean(values):
    return round(statistics.mean(values), 4) if values else None


def _safe_stdev(values):
    return round(statistics.stdev(values), 4) if len(values) >= 2 else None


def aggregate_writer_results(sample_results: list[dict]) -> dict:
    """Aggregate Test Writer per-sample metrics."""
    def vals(key):
        return [s["metrics"][key] for s in sample_results if s["metrics"].get(key) is not None]

    pass_at_1 = [1.0 if s["metrics"].get("pass_at_1") else 0.0 for s in sample_results]
    exec_success = [1.0 if s["metrics"].get("execution_success") else 0.0 for s in sample_results]
    latencies = [s["metrics"].get("latency_seconds") for s in sample_results if s["metrics"].get("latency_seconds") is not None]
    tokens = [s["metrics"].get("llm_total_tokens") for s in sample_results if s["metrics"].get("llm_total_tokens") is not None]

    by_category: dict[str, dict] = {}
    for s in sample_results:
        cat = s["sample"].get("category", "unknown")
        by_category.setdefault(cat, []).append(s)

    category_summary = {}
    for cat, items in by_category.items():
        cat_pass = [1.0 if i["metrics"].get("pass_at_1") else 0.0 for i in items]
        category_summary[cat] = {
            "n": len(items),
            "pass_at_1": _safe_mean(cat_pass),
        }

    return {
        "n_samples": len(sample_results),
        "execution_success_rate": _safe_mean(exec_success),
        "pass_at_1": _safe_mean(pass_at_1),
        "line_coverage_mean": _safe_mean(vals("line_coverage")),
        "branch_coverage_mean": _safe_mean(vals("branch_coverage")),
        "mutation_score_mean": _safe_mean(vals("mutation_score")),
        "hallucination_rate_mean": _safe_mean(vals("hallucination_rate")),
        "latency_seconds_mean": _safe_mean(latencies),
        "latency_seconds_stdev": _safe_stdev(latencies),
        "tokens_mean": _safe_mean(tokens),
        "bleu_4_mean": _safe_mean(vals("bleu_4")),
        "rouge_l_mean": _safe_mean(vals("rouge_l")),
        "codebleu_simplified_mean": _safe_mean(vals("codebleu_simplified")),
        "by_category": category_summary,
        "note_textsim": "BLEU/ROUGE/CodeBLEU are text-similarity only, never correctness",
    }


def aggregate_debugger_results(sample_results: list[dict]) -> dict:
    """Aggregate Debugger per-sample metrics."""
    def vals(key):
        return [s["metrics"][key] for s in sample_results if s["metrics"].get(key) is not None]

    return {
        "n_samples": len(sample_results),
        "repair_success_rate": _safe_mean(vals("repair_success_ratio")),
        "test_recovery_rate_mean": _safe_mean(vals("test_recovery_rate")),
        "first_attempt_repair_rate": _safe_mean(vals("first_attempt_repair_ratio")),
        "regression_rate": _safe_mean(vals("regression_ratio")),
        "iterations_mean": _safe_mean(vals("iterations_used")),
        "latency_seconds_mean": _safe_mean(vals("latency_seconds")),
        "per_failure_kind": {
            kind: {
                "n": len(items),
                "repair_success_rate": _safe_mean([
                    1.0 if i["metrics"].get("repair_success") else 0.0 for i in items
                ]),
            }
            for kind, items in _group_by(sample_results, lambda s: s["metrics"].get("failure_kind") or "unknown").items()
        },
    }


def _group_by(items, key_fn):
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(key_fn(item), []).append(item)
    return groups


def write_aggregated(exp_dir: Path, aggregated: dict) -> Path:
    """Write aggregated.json inside the experiment directory."""
    out = Path(exp_dir) / "aggregated.json"
    write_json_scrubbed(out, aggregated)
    return out


COMPARISON_COLUMNS = [
    ("experiment", "Experiment"),
    ("model", "Model"),
    ("prompt_version", "Prompt"),
    ("rag_status", "RAG"),
    ("pass_at_1", "Pass@1"),
    ("line_coverage_mean", "Coverage"),
    ("branch_coverage_mean", "BranchCov"),
    ("mutation_score_mean", "Mutation"),
    ("hallucination_rate_mean", "Halluc."),
    ("latency_seconds_mean", "Latency(s)"),
    ("tokens_mean", "Tokens"),
    ("repair_success_rate", "RepairRate"),
    ("first_attempt_repair_rate", "FirstAttempt"),
    ("regression_rate", "Regression"),
]


def comparison_markdown(experiments: list[dict]) -> str:
    """
    Build the comparison table across experiment aggregates.

    Each entry: metadata fields + aggregate fields (writer and/or debugger).
    """
    lines = ["# Experiment Comparison", ""]
    writer_rows = [e for e in experiments if "pass_at_1" in e.get("aggregate", {})]
    debug_rows = [e for e in experiments if "repair_success_rate" in e.get("aggregate", {})]

    if writer_rows:
        lines += ["## Test Writer", ""]
        header = [label for key, label in COMPARISON_COLUMNS if key != "repair_success_rate" and key != "first_attempt_repair_rate" and key != "regression_rate"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for exp in writer_rows:
            agg = exp["aggregate"]
            meta = exp.get("metadata", {})
            row = {
                "experiment": exp.get("experiment_id", meta.get("experiment", "?")),
                "model": meta.get("model", "?"),
                "prompt_version": meta.get("prompt_version", "?"),
                "rag_status": "ON" if meta.get("rag_enabled") else "OFF",
                **agg,
            }
            cells = []
            for key, label in COMPARISON_COLUMNS:
                if key in ("repair_success_rate", "first_attempt_repair_rate", "regression_rate"):
                    continue
                value = row.get(key)
                cells.append("—" if value is None else str(value))
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    if debug_rows:
        lines += ["## Debugger", ""]
        header = ["Experiment", "Model", "RepairRate", "Recovery", "FirstAttempt", "Regression", "Iterations", "Latency(s)"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for exp in debug_rows:
            agg = exp["aggregate"]
            meta = exp.get("metadata", {})
            lines.append("| " + " | ".join([
                exp.get("experiment_id", meta.get("experiment", "?")),
                meta.get("model", "?"),
                str(agg.get("repair_success_rate", "—")),
                str(agg.get("test_recovery_rate_mean", "—")),
                str(agg.get("first_attempt_repair_rate", "—")),
                str(agg.get("regression_rate", "—")),
                str(agg.get("iterations_mean", "—")),
                str(agg.get("latency_seconds_mean", "—")),
            ]) + " |")
        lines.append("")

    lines.append("_Text-similarity metrics (BLEU/ROUGE/CodeBLEU) are excluded from this table: "
                 "they are similarity measures, never correctness measures._")
    return "\n".join(lines)
