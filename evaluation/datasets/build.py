"""
Materialize the dataset to disk with a SHA-256 manifest.

Building is a pure function of datasets/corpus.py — rebuilding the same
version twice yields byte-identical files and an identical manifest hash
(reproducibility guarantee).
"""

import hashlib
import json
from pathlib import Path

from evaluation.config import DATASET_VERSION, GENERATED_DATASETS_DIR, DATASETS_DIR
from evaluation.datasets.corpus import ALL_SAMPLES
from evaluation.isolation import ensure_under_evaluation


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_dataset(version: str = DATASET_VERSION, force: bool = False) -> dict:
    """Write every sample to generated/<version>/ and return the manifest."""
    root = ensure_under_evaluation(GENERATED_DATASETS_DIR / version)
    manifest: dict = {
        "dataset_version": version,
        "samples": [],
        "files": {},
    }

    for sample in ALL_SAMPLES:
        sample_dir = root / sample.sample_id
        sample_dir.mkdir(parents=True, exist_ok=True)

        source_dir = sample_dir / "source"
        source_dir.mkdir(exist_ok=True)
        for rel_path, content in sample.files.items():
            target = source_dir / rel_path
            target.write_text(content, encoding="utf-8")
            manifest["files"][f"{sample.sample_id}/source/{rel_path}"] = _sha256(content)

        if sample.reference_test is not None:
            ref = sample_dir / "reference_test.py"
            ref.write_text(sample.reference_test, encoding="utf-8")
            manifest["files"][f"{sample.sample_id}/reference_test.py"] = _sha256(sample.reference_test)

        if sample.buggy_test is not None:
            buggy = sample_dir / "buggy_test.py"
            buggy.write_text(sample.buggy_test, encoding="utf-8")
            manifest["files"][f"{sample.sample_id}/buggy_test.py"] = _sha256(sample.buggy_test)

        manifest["samples"].append({
            "sample_id": sample.sample_id,
            "category": sample.category,
            "difficulty": sample.difficulty,
            "description": sample.description,
            "entry_file": sample.entry_file,
            "has_reference_test": sample.reference_test is not None,
            "is_debug_target": sample.is_debug_target,
            "buggy_failure_kind": sample.buggy_failure_kind,
            "tags": list(sample.tags),
        })

    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False)
    (root / "manifest.json").write_text(manifest_bytes, encoding="utf-8")
    manifest["dataset_hash"] = hashlib.sha256(manifest_bytes.encode("utf-8")).hexdigest()[:16]
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def dataset_root(version: str = DATASET_VERSION) -> Path:
    root = ensure_under_evaluation(GENERATED_DATASETS_DIR / version)
    if not root.exists():
        build_dataset(version)
    return root


def load_dataset_index(version: str = DATASET_VERSION) -> dict:
    manifest_path = dataset_root(version) / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def dataset_fingerprint(version: str = DATASET_VERSION) -> str:
    """Stable fingerprint recorded in every experiment's metadata."""
    return load_dataset_index(version)["dataset_hash"]


if __name__ == "__main__":
    manifest = build_dataset()
    print(f"dataset {DATASET_VERSION} built: {len(manifest['samples'])} samples, "
          f"{len(manifest['files'])} files, hash {manifest['dataset_hash']}")
    print(f"location: {DATASETS_DIR / 'generated' / DATASET_VERSION}")
