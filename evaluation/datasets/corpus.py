"""
Deterministic evaluation corpus — 12 samples across 8 categories.

Every string is fixed; building the dataset is a pure function of this file.
Reference tests are text-similarity ground truth ONLY (never correctness
oracles). Buggy tests are controlled failures with a known repair family.
"""

from evaluation.datasets.spec import SampleSpec


def _test_header(module: str) -> str:
    """Import header used by shipped reference/buggy tests (same convention
    as production-generated tests: source dir on sys.path)."""
    return (
        "import sys\n"
        "import os\n"
        "import pytest\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))\n"
        f"from {module} import *\n"
    )


_SIMPLE_001_SRC = '''def add(a, b):
    """Return the sum of a and b."""
    return a + b


def sub(a, b):
    """Return a minus b."""
    return a - b
'''

_SIMPLE_001_REF = '''def test_add():
    assert add(2, 3) == 5


def test_sub():
    assert sub(5, 2) == 3
'''

_SIMPLE_002_SRC = '''def greet(name):
    """Return a greeting; empty name falls back to 'world'."""
    if not name:
        name = "world"
    return f"Hello, {name}!"
'''

_SIMPLE_002_REF = '''def test_greet_name():
    assert greet("Ada") == "Hello, Ada!"


def test_greet_empty():
    assert greet("") == "Hello, world!"
'''

_BRANCH_001_SRC = '''def classify_grade(score):
    """Classify a 0-100 score into a letter grade."""
    if score < 0 or score > 100:
        raise ValueError("score must be between 0 and 100")
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"
'''

_BRANCH_001_REF = '''def test_grades():
    assert classify_grade(95) == "A"
    assert classify_grade(85) == "B"
    assert classify_grade(75) == "C"
    assert classify_grade(65) == "D"
    assert classify_grade(10) == "F"


def test_invalid():
    import pytest
    with pytest.raises(ValueError):
        classify_grade(-1)
'''

_BRANCH_002_SRC = '''def shipping_cost(weight_kg, express):
    """Compute shipping cost with weight tiers and an express surcharge."""
    if weight_kg <= 0:
        raise ValueError("weight must be positive")
    if weight_kg <= 1:
        cost = 5.0
    elif weight_kg <= 5:
        cost = 10.0
    elif weight_kg <= 20:
        cost = 25.0
    else:
        cost = 50.0
    if express:
        cost = cost * 2
    return cost
'''

_BRANCH_002_REF = '''def test_tiers():
    assert shipping_cost(0.5, False) == 5.0
    assert shipping_cost(3, False) == 10.0
    assert shipping_cost(10, False) == 25.0
    assert shipping_cost(30, False) == 50.0


def test_express():
    assert shipping_cost(3, True) == 20.0
'''

_EDGE_001_SRC = '''def clamp(value, low, high):
    """Clamp value into [low, high]; inverted bounds raise ValueError."""
    if low > high:
        raise ValueError("low must be <= high")
    return max(low, min(high, value))
'''

_EDGE_001_REF = '''def test_boundaries():
    assert clamp(5, 0, 10) == 5
    assert clamp(-3, 0, 10) == 0
    assert clamp(42, 0, 10) == 10


def test_equal_bounds():
    assert clamp(7, 5, 5) == 5
'''

_EDGE_002_SRC = '''def moving_average(values, window):
    """Moving average over `window`-sized slices; window must fit the data."""
    if window <= 0:
        raise ValueError("window must be positive")
    if window > len(values):
        raise ValueError("window larger than data")
    if not values:
        return []
    return [sum(values[i:i + window]) / window for i in range(len(values) - window + 1)]
'''

_EDGE_002_REF = '''def test_basic():
    assert moving_average([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]


def test_empty():
    assert moving_average([], 1) == []
'''

_EXC_001_SRC = '''def parse_positive_int(text):
    """Parse a strictly positive integer; raise ValueError on bad input."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    value = int(text)
    if value <= 0:
        raise ValueError(f"expected a positive integer, got {value}")
    return value
'''

_EXC_001_REF = '''def test_valid():
    assert parse_positive_int("42") == 42


def test_errors():
    import pytest
    with pytest.raises(TypeError):
        parse_positive_int(12)
    with pytest.raises(ValueError):
        parse_positive_int("-5")
'''

_CLASS_001_SRC = '''class Rectangle:
    """A rectangle with validated dimensions."""

    def __init__(self, width, height):
        if width <= 0 or height <= 0:
            raise ValueError("dimensions must be positive")
        self.width = width
        self.height = height

    def area(self):
        return self.width * self.height

    def perimeter(self):
        return 2 * (self.width + self.height)

    def scale(self, factor):
        """Return a new Rectangle scaled by factor."""
        if factor <= 0:
            raise ValueError("factor must be positive")
        return Rectangle(self.width * factor, self.height * factor)
'''

_CLASS_001_REF = '''def test_rect():
    r = Rectangle(3, 4)
    assert r.area() == 12
    assert r.perimeter() == 14


def test_scale():
    r = Rectangle(2, 3).scale(2)
    assert r.area() == 24
'''

_CLASS_002_SRC = '''class BankAccount:
    """A minimal bank account with overdraft protection."""

    def __init__(self, owner, balance=0):
        self.owner = owner
        self.balance = balance
        self.history = []

    def deposit(self, amount):
        if amount <= 0:
            raise ValueError("deposit must be positive")
        self.balance += amount
        self.history.append(("deposit", amount))
        return self.balance

    def withdraw(self, amount):
        if amount <= 0:
            raise ValueError("withdrawal must be positive")
        if amount > self.balance:
            raise ValueError("insufficient funds")
        self.balance -= amount
        self.history.append(("withdraw", amount))
        return self.balance
'''

_CLASS_002_REF = '''def test_flow():
    acc = BankAccount("Ada", 100)
    assert acc.deposit(50) == 150
    assert acc.withdraw(30) == 120
    assert len(acc.history) == 2
'''

_DEP_HELPERS_SRC = '''def median(values):
    """Median of a non-empty list of numbers."""
    if not values:
        raise ValueError("empty data")
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
'''

_DEP_REPORT_SRC = '''import math

from helpers import median


def describe(values):
    """Basic descriptive statistics; delegates the median to helpers."""
    if not values:
        raise ValueError("empty data")
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "median": median(values),
        "stdev": math.sqrt(sum((v - sum(values) / len(values)) ** 2 for v in values) / len(values)),
    }
'''

_DEP_REPORT_REF = '''def test_describe():
    stats = describe([1, 2, 3, 4])
    assert stats["count"] == 4
    assert stats["median"] == 2.5
    assert stats["max"] == 4
'''

_DIFF_001_SRC = '''def merge_intervals(intervals):
    """Merge overlapping [start, end] intervals; input may be unsorted."""
    if not intervals:
        return []
    for start, end in intervals:
        if start > end:
            raise ValueError("invalid interval")
    ordered = sorted(intervals)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [tuple(pair) for pair in merged]
'''

_DIFF_001_REF = '''def test_merge():
    assert merge_intervals([(1, 3), (2, 6), (8, 10)]) == [(1, 6), (8, 10)]
    assert merge_intervals([]) == []
    assert merge_intervals([(5, 5)]) == [(5, 5)]
'''

_DIFF_002_SRC = '''def flatten_dict(nested, prefix=""):
    """Flatten a nested dict into {'a.b.c': value} pairs."""
    items = {}
    for key, value in nested.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            items.update(flatten_dict(value, prefix=path))
        else:
            items[path] = value
    return items
'''

_DIFF_002_REF = '''def test_flatten():
    assert flatten_dict({"a": {"b": 1}}) == {"a.b": 1}
    assert flatten_dict({}) == {}
    assert flatten_dict({"x": 1}) == {"x": 1}
'''


# ── Controlled debugging targets ──────────────────────────────────────────

_DEBUG_001_SRC = '''def add(a, b):
    """Return the sum of a and b."""
    return a + b


def multiply(a, b):
    """Return the product of a and b."""
    return a * b
'''

# Buggy test: wrong expected value (off-by-one style mistake)
_DEBUG_001_BUGGY = _test_header("sample_debug_add") + '''

def test_add():
    assert add(2, 3) == 6


def test_add_negative():
    assert add(-1, -2) == -3


def test_multiply():
    assert multiply(3, 4) == 12
'''

_DEBUG_002_SRC = '''def parse_port(text):
    """Parse a port number (1-65535). Raises TypeError on non-int input."""
    if not isinstance(text, int):
        raise TypeError("port must be an integer")
    if not 1 <= text <= 65535:
        raise ValueError("port out of range")
    return text
'''

# Buggy test: expects ValueError but the code raises TypeError
_DEBUG_002_BUGGY = _test_header("sample_debug_ports") + '''

def test_parse_port_string_raises_value_error():
    with pytest.raises(ValueError):
        parse_port("8080")


def test_parse_port_valid():
    assert parse_port(8080) == 8080
'''

_DEBUG_003_SRC = '''import json


def encode_payload(data):
    """Serialize data to a compact JSON string."""
    return json.dumps(data, separators=(",", ":"))
'''

# Buggy test: patches a non-existent target
_DEBUG_003_BUGGY = _test_header("sample_debug_payload") + '''

from unittest.mock import patch


def test_encode_uses_json_dumps():
    with patch("sample_debug_payload.json.tool") as dumps_mock:
        dumps_mock.return_value = "{}"
        assert encode_payload({"a": 1}) == "{}"
'''


# ── RAG retrieval ground truth ────────────────────────────────────────────
# Seeded pattern corpus for the isolated retrieval evaluation. Each entry
# mirrors utils.rag store_pattern arguments; `functions` lists the query
# functions for which this pattern counts as relevant.

PATTERN_CORPUS = [
    {
        "function_name": "add",
        "function_signature": "def add(a, b)",
        "error_type": "AssertionError",
        "root_cause": "expected value hardcoded incorrectly in the generated test",
        "fix_applied": "correct the expected constant to match the real return value",
        "functions": ["add"],
    },
    {
        "function_name": "parse_port",
        "function_signature": "def parse_port(text)",
        "error_type": "Failed",
        "root_cause": "test expects ValueError but the implementation raises TypeError for non-int input",
        "fix_applied": "change pytest.raises to the exception type the source actually raises",
        "functions": ["parse_port", "parse_positive_int"],
    },
    {
        "function_name": "encode_payload",
        "function_signature": "def encode_payload(data)",
        "error_type": "AttributeError",
        "root_cause": "test patches a module attribute that does not exist",
        "fix_applied": "patch the real imported object used by the function under test",
        "functions": ["encode_payload"],
    },
    {
        "function_name": "withdraw",
        "function_signature": "def withdraw(self, amount)",
        "error_type": "ValueError",
        "root_cause": "withdrawal larger than balance must raise but tests call it with valid funds",
        "fix_applied": "construct the fixture so the error path is actually exercised",
        "functions": ["withdraw", "book_status"],
    },
    {
        "function_name": "classify_grade",
        "function_signature": "def classify_grade(score)",
        "error_type": "AssertionError",
        "root_cause": "boundary values (90/80/70/60) mishandled by the generated tests",
        "fix_applied": "assert both sides of every boundary",
        "functions": ["classify_grade", "shipping_cost"],
    },
    {
        "function_name": "scale",
        "function_signature": "def scale(self, factor)",
        "error_type": "TypeError",
        "root_cause": "constructor arguments missing when instantiating the class under test",
        "fix_applied": "pass constructor arguments matching __init__ types",
        "functions": ["scale", "Rectangle"],
    },
]


ALL_SAMPLES: list[SampleSpec] = [
    SampleSpec(
        sample_id="SIMPLE-001", category="simple", difficulty="easy",
        description="Pure arithmetic functions, no branching.",
        files={"sample_simple.py": _SIMPLE_001_SRC}, entry_file="sample_simple.py",
        reference_test=_test_header("sample_simple") + _SIMPLE_001_REF,
        tags=("arithmetic", "pure"),
    ),
    SampleSpec(
        sample_id="SIMPLE-002", category="simple", difficulty="easy",
        description="String formatting with one default branch.",
        files={"sample_greet.py": _SIMPLE_002_SRC}, entry_file="sample_greet.py",
        reference_test=_test_header("sample_greet") + _SIMPLE_002_REF,
        tags=("strings",),
    ),
    SampleSpec(
        sample_id="BRANCH-001", category="branch", difficulty="easy",
        description="Grade classifier: five-way branch plus input validation.",
        files={"sample_grades.py": _BRANCH_001_SRC}, entry_file="sample_grades.py",
        reference_test=_test_header("sample_grades") + _BRANCH_001_REF,
        tags=("branches", "boundaries"),
    ),
    SampleSpec(
        sample_id="BRANCH-002", category="branch", difficulty="medium",
        description="Shipping cost: weight tiers plus a boolean surcharge.",
        files={"sample_shipping.py": _BRANCH_002_SRC}, entry_file="sample_shipping.py",
        reference_test=_test_header("sample_shipping") + _BRANCH_002_REF,
        tags=("branches", "floats"),
    ),
    SampleSpec(
        sample_id="EDGE-001", category="edge", difficulty="easy",
        description="Clamping with inverted-bound rejection.",
        files={"sample_clamp.py": _EDGE_001_SRC}, entry_file="sample_clamp.py",
        reference_test=_test_header("sample_clamp") + _EDGE_001_REF,
        tags=("edges",),
    ),
    SampleSpec(
        sample_id="EDGE-002", category="edge", difficulty="medium",
        description="Moving average with empty-data and window validation.",
        files={"sample_moving_avg.py": _EDGE_002_SRC}, entry_file="sample_moving_avg.py",
        reference_test=_test_header("sample_moving_avg") + _EDGE_002_REF,
        tags=("edges", "sequences"),
    ),
    SampleSpec(
        sample_id="EXC-001", category="exception", difficulty="medium",
        description="Strict parser with TypeError vs ValueError distinction.",
        files={"sample_parser.py": _EXC_001_SRC}, entry_file="sample_parser.py",
        reference_test=_test_header("sample_parser") + _EXC_001_REF,
        tags=("exceptions",),
    ),
    SampleSpec(
        sample_id="CLASS-001", category="class", difficulty="medium",
        description="Rectangle value object: constructor validation + immutable-style scale().",
        files={"sample_rect.py": _CLASS_001_SRC}, entry_file="sample_rect.py",
        reference_test=_test_header("sample_rect") + _CLASS_001_REF,
        tags=("classes",),
    ),
    SampleSpec(
        sample_id="CLASS-002", category="class", difficulty="medium",
        description="BankAccount with history and overdraft rejection.",
        files={"sample_bank.py": _CLASS_002_SRC}, entry_file="sample_bank.py",
        reference_test=_test_header("sample_bank") + _CLASS_002_REF,
        tags=("classes", "state"),
    ),
    SampleSpec(
        sample_id="DEP-001", category="dependency", difficulty="medium",
        description="Two modules: report.py depends on helpers.median and math.",
        files={"helpers.py": _DEP_HELPERS_SRC, "sample_report.py": _DEP_REPORT_SRC},
        entry_file="sample_report.py",
        reference_test=_test_header("sample_report") + _DEP_REPORT_REF,
        tags=("dependencies",),
    ),
    SampleSpec(
        sample_id="DIFF-001", category="difficult", difficulty="hard",
        description="Interval merging: sorting, in-place merging, tuple conversion.",
        files={"sample_intervals.py": _DIFF_001_SRC}, entry_file="sample_intervals.py",
        reference_test=_test_header("sample_intervals") + _DIFF_001_REF,
        tags=("algorithm",),
    ),
    SampleSpec(
        sample_id="DIFF-002", category="difficult", difficulty="hard",
        description="Recursive dict flattening with prefix building.",
        files={"sample_flatten.py": _DIFF_002_SRC}, entry_file="sample_flatten.py",
        reference_test=_test_header("sample_flatten") + _DIFF_002_REF,
        tags=("recursion",),
    ),
    SampleSpec(
        sample_id="DEBUG-001", category="debug", difficulty="easy",
        description="Controlled failure: generated-style test with a wrong expected value.",
        files={"sample_debug_add.py": _DEBUG_001_SRC}, entry_file="sample_debug_add.py",
        buggy_test=_DEBUG_001_BUGGY, buggy_failure_kind="wrong_expected",
        expected_repair="change expected 6 to the correct sum 5",
        target_function="add",
        relevant_pattern_functions=["add"],
        tags=("debug", "assertion"),
    ),
    SampleSpec(
        sample_id="DEBUG-002", category="debug", difficulty="medium",
        description="Controlled failure: test expects ValueError, source raises TypeError.",
        files={"sample_debug_ports.py": _DEBUG_002_SRC}, entry_file="sample_debug_ports.py",
        buggy_test=_DEBUG_002_BUGGY, buggy_failure_kind="wrong_exception",
        expected_repair="expect TypeError instead of ValueError",
        target_function="parse_port",
        relevant_pattern_functions=["parse_port"],
        tags=("debug", "exception-type"),
    ),
    SampleSpec(
        sample_id="DEBUG-003", category="debug", difficulty="hard",
        description="Controlled failure: test patches a module attribute that does not exist.",
        files={"sample_debug_payload.py": _DEBUG_003_SRC}, entry_file="sample_debug_payload.py",
        buggy_test=_DEBUG_003_BUGGY, buggy_failure_kind="wrong_patch",
        expected_repair="patch json.dumps (the real dependency), not json.tool",
        target_function="encode_payload",
        relevant_pattern_functions=["encode_payload"],
        tags=("debug", "mocking"),
    ),
]


def get_sample(sample_id: str) -> SampleSpec:
    for sample in ALL_SAMPLES:
        if sample.sample_id == sample_id:
            return sample
    raise KeyError(f"Unknown sample id: {sample_id}")


def writer_samples() -> list[SampleSpec]:
    """Samples used by Test Writer experiments (non-debug categories)."""
    return [s for s in ALL_SAMPLES if not s.is_debug_target]
