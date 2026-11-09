"""Dataset layer: deterministic, versioned evaluation samples."""

from evaluation.datasets.spec import SampleSpec
from evaluation.datasets.build import build_dataset, load_dataset_index

__all__ = ["SampleSpec", "build_dataset", "load_dataset_index"]
