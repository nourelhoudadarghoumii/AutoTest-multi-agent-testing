"""
CLI: run a GenAI evaluation experiment.

    python -m evaluation.run_experiment --experiment baseline
    python -m evaluation.run_experiment --experiment prompts [--full]
    python -m evaluation.run_experiment --experiment rag
    python -m evaluation.run_experiment --experiment retrieval
    python -m evaluation.run_experiment --experiment models --writer-model <slug>
    python -m evaluation.run_experiment --experiment debugger [--full] [--debugger-model <slug>]

Common flags:
    --samples N       limit to the first N samples (default: smoke = 2, full = all)
    --full            run the entire dataset
    --no-mutation     skip mutation testing (default OFF unless --full)
    --writer-model X  override the Test Writer model (model comparison only)
    --debugger-model Y  override the Debugger model (model comparison only)

Methodology: BASELINE → CHANGE ONE VARIABLE → SAME DATASET → MEASURE →
COMPARE → ANALYZE TRADE-OFFS → NEXT EXPERIMENT. Results are append-only.
"""

import argparse
import json
import sys

from evaluation.config import SMOKE_SAMPLES, SMOKE_MUTATION
from evaluation.datasets.corpus import ALL_SAMPLES


def _sample_ids_for(args) -> list[str] | None:
    if args.full:
        return None
    if args.samples:
        return [s.sample_id for s in ALL_SAMPLES[: args.samples]]
    return [s.sample_id for s in ALL_SAMPLES[:SMOKE_SAMPLES]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an AutoTest evaluation experiment")
    parser.add_argument("--experiment", required=True,
                        choices=["baseline", "prompts", "rag", "retrieval", "models", "debugger", "mutation_guided", "mutation_guided_validated"])
    parser.add_argument("--full", action="store_true", help="run the full dataset")
    parser.add_argument("--samples", type=int, default=None, help="limit to first N samples")
    parser.add_argument("--sample", default=None, help="single sample id (mutation_guided)")
    parser.add_argument("--no-mutation", action="store_true", help="disable mutation scoring")
    parser.add_argument("--mutation", action="store_true", help="enable mutation scoring")
    parser.add_argument("--writer-model", default=None, help="override Test Writer model")
    parser.add_argument("--debugger-model", default=None, help="override Debugger model")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    sample_ids = _sample_ids_for(args)
    # Mutation: off by default; --full enables it unless --no-mutation;
    # explicit --mutation always wins.
    mutation = SMOKE_MUTATION
    if args.mutation:
        mutation = True
    elif args.full and not args.no_mutation:
        mutation = True

    from evaluation.experiments import (
        run_baseline,
        run_debugger_experiment,
        run_model_comparison,
        run_prompt_variants,
        run_rag_ab,
        run_retrieval_evaluation,
    )
    from evaluation.metrics.aggregate import comparison_markdown
    from evaluation.security import write_json_scrubbed
    from evaluation.config import REPORTS_DIR
    from pathlib import Path

    if args.experiment == "mutation_guided_validated":
        from evaluation.experiments.mutation_guided_validated import run_mutation_guided_validated
        exp_dirs = [run_mutation_guided_validated(
            sample_ids=[args.sample] if args.sample else None,
            max_mutants=8,
        )]
    elif args.experiment == "mutation_guided":
        from evaluation.experiments.mutation_guided import run_mutation_guided_experiment
        exp_dirs = [run_mutation_guided_experiment(
            sample_ids=[args.sample] if args.sample else None,
            max_mutants=8,
        )]
    elif args.experiment == "baseline":
        exp_dirs = [run_baseline(
            mutation=mutation,
            sample_ids=sample_ids,
            writer_model=args.writer_model,
        )]
    elif args.experiment == "prompts":
        exp_dirs = run_prompt_variants(
            mutation=mutation,
            sample_ids=sample_ids,
            writer_model=args.writer_model,
        )
    elif args.experiment == "rag":
        exp_dirs = run_rag_ab(
            mutation=mutation,
            sample_ids=sample_ids,
        )
    elif args.experiment == "retrieval":
        exp_dirs = [run_retrieval_evaluation()]
    elif args.experiment == "models":
        if not args.writer_model:
            parser.error("--experiment models requires --writer-model <openrouter-slug>")
        exp_dirs = run_model_comparison(
            writer_models=[args.writer_model],
            mutation=mutation,
            sample_ids=sample_ids,
        )
    elif args.experiment == "debugger":
        exp_dirs = [run_debugger_experiment(
            debugger_model=args.debugger_model,
            sample_ids=sample_ids,
        )]
    else:  # pragma: no cover
        parser.error(f"unknown experiment {args.experiment}")

    # Persist a cross-run comparison report under evaluation/reports/
    entries = []
    for exp_dir in exp_dirs:
        metadata = json.loads((exp_dir / "metadata.json").read_text(encoding="utf-8"))
        aggregate = json.loads((exp_dir / "aggregated.json").read_text(encoding="utf-8"))
        entries.append({"experiment_id": exp_dir.name, "metadata": metadata, "aggregate": aggregate})

    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = Path(REPORTS_DIR) / f"comparison_{args.experiment}_{exp_dirs[0].name.split('_', 1)[1]}.md"
    report_path.write_text(comparison_markdown(entries), encoding="utf-8")

    print(f"\nexperiment(s) stored under: {exp_dirs[0].parent}")
    for exp_dir in exp_dirs:
        aggregate = json.loads((exp_dir / "aggregated.json").read_text(encoding="utf-8"))
        print(f"  {exp_dir.name}: {json.dumps({k: v for k, v in aggregate.items() if not isinstance(v, (dict, list))}, ensure_ascii=False)}")
    print(f"comparison report: {report_path}")


if __name__ == "__main__":
    main()
