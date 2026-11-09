"""
CLI: materialize the evaluation dataset.

    python -m evaluation.build_dataset [--force]

Deterministic: identical rebuilds produce an identical manifest hash.
"""

import argparse

from evaluation.datasets.build import build_dataset, load_dataset_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the AutoTest evaluation dataset")
    parser.add_argument("--force", action="store_true", help="rebuild even if present")
    args = parser.parse_args()

    manifest = build_dataset(force=args.force)
    index = load_dataset_index()

    print(f"dataset version : {index['dataset_version']}")
    print(f"samples         : {len(index['samples'])}")
    print(f"files           : {len(index['files'])}")
    print(f"dataset hash    : {index['dataset_hash']}")
    print("categories      :", ", ".join(sorted({s['category'] for s in index['samples']})))


if __name__ == "__main__":
    main()
