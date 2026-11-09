"""
SampleSpec — one evaluation sample.

A sample is a small, deterministic Python unit with:
    - source file(s) handed to the Test Writer
    - a reference test (text-similarity ground truth only — never a
      correctness oracle)
    - for DEBUG targets: a controlled buggy test (known failure + known
      repair family) and the retrieval ground truth
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SampleSpec:
    sample_id: str                    # unique, e.g. "BRANCH-001"
    category: str                     # simple|branch|edge|exception|class|dependency|difficult|debug
    difficulty: str                   # easy|medium|hard
    description: str
    files: dict[str, str]             # relative path -> source code
    entry_file: str                   # main file the Test Writer targets
    reference_test: str | None = None        # ground truth for text similarity ONLY
    buggy_test: str | None = None            # controlled failing test (debug targets)
    buggy_failure_kind: str | None = None    # wrong_expected|wrong_exception|wrong_patch
    expected_repair: str | None = None       # human description of the repair family
    target_function: str | None = None       # debug/retrieval target function
    relevant_pattern_functions: list[str] = field(default_factory=list)  # retrieval ground truth
    tags: tuple[str, ...] = ()

    @property
    def is_debug_target(self) -> bool:
        return self.category == "debug"
