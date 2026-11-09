"""
CLI: evaluation smoke test.

    python -m evaluation.smoke

Runs 2 writer samples (real LLM, no mutation) + 1 debugger sample and
prints a compact summary. Purpose: fast end-to-end sanity check of the
evaluation layer — NOT a statistically meaningful measurement.
"""

import json


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    from evaluation.datasets.corpus import ALL_SAMPLES
    from evaluation.experiments import run_baseline, run_debugger_experiment
    from evaluation.security import contains_secret
    from pathlib import Path

    print("=== Evaluation smoke test (2 writer samples + 1 debug sample, no mutation) ===\n")

    writer_sample_ids = [s.sample_id for s in ALL_SAMPLES if not s.is_debug_target][:2]
    debug_sample_ids = ["DEBUG-001"]

    exp_dir = run_baseline(sample_ids=writer_sample_ids, mutation=False,
                           notes="smoke test")
    metadata = json.loads((exp_dir / "metadata.json").read_text(encoding="utf-8"))
    aggregate = json.loads((exp_dir / "aggregated.json").read_text(encoding="utf-8"))

    print(f"baseline experiment : {exp_dir.name}")
    print(f"  model             : {metadata['model']}")
    print(f"  prompt            : {metadata['prompt_version']}")
    print(f"  pass@1            : {aggregate['pass_at_1']}")
    print(f"  execution success : {aggregate['execution_success_rate']}")
    print(f"  line coverage     : {aggregate['line_coverage_mean']}")
    print(f"  branch coverage   : {aggregate['branch_coverage_mean']}")
    print(f"  hallucination     : {aggregate['hallucination_rate_mean']}")

    debug_dir = run_debugger_experiment(sample_ids=debug_sample_ids, notes="smoke test")
    debug_agg = json.loads((debug_dir / "aggregated.json").read_text(encoding="utf-8"))
    print(f"\ndebugger experiment : {debug_dir.name}")
    print(f"  repair success    : {debug_agg['repair_success_rate']}")
    print(f"  recovery rate     : {debug_agg['test_recovery_rate_mean']}")
    print(f"  iterations (mean) : {debug_agg['iterations_mean']}")

    # Secret scan over everything just written
    leaked = False
    for root in (exp_dir, debug_dir):
        for result_file in Path(root).rglob("*.json"):
            if contains_secret(json.loads(result_file.read_text(encoding="utf-8"))):
                leaked = True
                print(f"  !! potential secret in {result_file}")
    print(f"\nsecret scan         : {'LEAK DETECTED' if leaked else 'clean'}")
    print(f"\nresults stored under: {exp_dir.parent}")


if __name__ == "__main__":
    main()
