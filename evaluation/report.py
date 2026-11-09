"""
CLI: build a comparison report across stored experiments.

    python -m evaluation.report --latest              # latest experiment of each name
    python -m evaluation.report --experiments id1 id2 # explicit experiment ids
"""

import argparse
import json
from pathlib import Path

from evaluation.config import RESULTS_DIR, REPORTS_DIR
from evaluation.metrics.aggregate import comparison_markdown


def _exp_key(dir_name: str) -> str:
    """Strip the trailing _<timestamp>_<uid> to group runs of the same experiment."""
    parts = dir_name.rsplit("_", 2)
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        return parts[0]
    return dir_name


def _latest_by_name() -> list[dict]:
    entries = []
    by_name: dict[str, Path] = {}
    for exp_dir in sorted(RESULTS_DIR.iterdir()):
        if not exp_dir.is_dir() or not (exp_dir / "aggregated.json").exists():
            continue
        by_name[_exp_key(exp_dir.name)] = exp_dir  # sorted order → latest wins
    for name, exp_dir in by_name.items():
        metadata = json.loads((exp_dir / "metadata.json").read_text(encoding="utf-8"))
        aggregate = json.loads((exp_dir / "aggregated.json").read_text(encoding="utf-8"))
        entries.append({"experiment_id": exp_dir.name, "metadata": metadata, "aggregate": aggregate})
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an experiment comparison report")
    parser.add_argument("--latest", action="store_true", help="latest experiment per type")
    parser.add_argument("--experiments", nargs="+", help="explicit experiment directory names")
    args = parser.parse_args()

    if args.experiments:
        entries = []
        for exp_name in args.experiments:
            exp_dir = RESULTS_DIR / exp_name
            if not (exp_dir / "aggregated.json").exists():
                print(f"skipping {exp_name}: no aggregated.json")
                continue
            metadata = json.loads((exp_dir / "metadata.json").read_text(encoding="utf-8"))
            aggregate = json.loads((exp_dir / "aggregated.json").read_text(encoding="utf-8"))
            entries.append({"experiment_id": exp_dir.name, "metadata": metadata, "aggregate": aggregate})
    else:
        entries = _latest_by_name()

    if not entries:
        print("no stored experiments found — run an experiment first")
        return

    markdown = comparison_markdown(entries)
    out_path = REPORTS_DIR / "comparison_latest.md"
    out_path.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"\nwritten to: {out_path}")


if __name__ == "__main__":
    main()
