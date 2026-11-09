"""
Mutation testing with a bounded, dependency-free AST mutation engine.

Mutants are single-node edits of the sample source:
    - arithmetic operator swaps        (+ <-> -, * <-> /)
    - comparison swaps                 (< <-> <=, > <-> >=, == <-> !=)
    - boolean connective swaps         (and <-> or)
    - constant perturbation            (n -> n+1, and True -> False / vice versa)

Score = killed / total (a mutant is killed when the generated test suite
fails against it). Bounded: at most max_mutants per sample.
"""

import ast
import copy
import re
import shutil
import subprocess
import sys
from pathlib import Path

from evaluation.config import MAX_MUTANTS_PER_SAMPLE

_SWAP_BINARY = {
    ast.Add: ast.Sub, ast.Sub: ast.Add,
    ast.Mult: ast.Div, ast.Div: ast.Mult,
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.And: ast.Or, ast.Or: ast.And,
}


class _MutationCollector(ast.NodeVisitor):
    """Collect (node, mutation) pairs for later application, one at a time."""

    def __init__(self):
        self.sites: list[tuple[str, int]] = []  # (kind, lineno)

    def visit_BinOp(self, node):
        if type(node.op) in _SWAP_BINARY:
            self.sites.append(("binop", node.lineno))
        self.generic_visit(node)

    def visit_Compare(self, node):
        for op in node.ops:
            if type(op) in _SWAP_BINARY:
                self.sites.append(("compare", node.lineno))
                break
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        if isinstance(node.op, (ast.And, ast.Or)):
            self.sites.append(("boolop", node.lineno))
        self.generic_visit(node)

    def visit_UnaryOp(self, node):
        if isinstance(node.op, ast.Not):
            self.sites.append(("not", node.lineno))
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, bool):
            self.sites.append(("boolconst", node.lineno))
        elif isinstance(node.value, int) and not isinstance(node.value, bool):
            self.sites.append(("intconst", node.lineno))
        self.generic_visit(node)


class _SingleMutator(ast.NodeTransformer):
    """Apply exactly one mutation (the nth matching site)."""

    def __init__(self, kind: str, index: int):
        self.kind = kind
        self.index = index
        self.seen = 0

    def _hit(self) -> bool:
        self.seen += 1
        return self.seen - 1 == self.index

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if self.kind == "binop" and type(node.op) in _SWAP_BINARY and self._hit():
            node.op = _SWAP_BINARY[type(node.op)]()
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        if self.kind == "compare" and any(type(op) in _SWAP_BINARY for op in node.ops) and self._hit():
            for i, op in enumerate(node.ops):
                if type(op) in _SWAP_BINARY:
                    node.ops[i] = _SWAP_BINARY[type(op)]()
                    break
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self.kind == "boolop" and self._hit():
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if self.kind == "not" and isinstance(node.op, ast.Not) and self._hit():
            # Drop the negation: replace `not X` with `X`
            return node.operand
        return node

    def visit_Constant(self, node):
        if self.kind == "boolconst" and isinstance(node.value, bool) and self._hit():
            return ast.Constant(value=not node.value)
        if self.kind == "intconst" and isinstance(node.value, int) and not isinstance(node.value, bool) and self._hit():
            return ast.Constant(value=node.value + 1)
        return node


def _mutant_sites(source: str) -> list[tuple[str, int]]:
    tree = ast.parse(source)
    collector = _MutationCollector()
    collector.visit(tree)
    # Deterministic order: by kind then source position
    return sorted(collector.sites, key=lambda s: (s[0], s[1]))


def generate_mutants(source: str, max_mutants: int = MAX_MUTANTS_PER_SAMPLE) -> list[dict]:
    """Produce up to `max_mutants` deterministic single-edit mutants."""
    sites = _mutant_sites(source)[:max_mutants]
    mutants = []
    per_kind_index: dict[str, int] = {}

    for kind, lineno in sites:
        per_kind_index.setdefault(kind, -1)
        per_kind_index[kind] += 1
        tree = ast.parse(source)
        mutator = _SingleMutator(kind, per_kind_index[kind])
        try:
            mutated = mutator.visit(tree)
            ast.fix_missing_locations(mutated)
            code = ast.unparse(mutated)
        except Exception:  # noqa: BLE001 — skip malformed mutants
            continue
        mutants.append({"kind": kind, "line": lineno, "source": code})
    return mutants


_FAILED_SUMMARY = re.compile(r"\b(\d+)\s+failed\b")


def _suite_kills_prepared(test_file: Path, mutant_source: str, entry_rel: str,
                          work_dir: Path, timeout: float) -> bool:
    """
    True iff the suite KILLS the mutant: pytest ran to completion and at
    least one test FAILED against the mutated copy.

    Strict kill semantics (post-audit):
      - timeouts are NOT counted as kills (inconclusive);
      - non-zero exits without an actual test failure (usage errors, exit 4;
        collection errors, exit 2) are NOT counted as kills;
      - a missing/unreadable test file is NOT counted as a kill.

    The test file is COPIED INTO the mutant workspace and the workspace copy
    is executed, so the module imported by the test IS the mutated copy
    (pytest's basedir insertion resolves imports from the test's directory).
    """
    if not Path(test_file).exists():
        return False
    (work_dir / entry_rel).write_text(mutant_source, encoding="utf-8")
    work_test = work_dir / Path(test_file).name
    shutil.copy(test_file, work_test)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header", "-x",
             "-p", "no:cacheprovider",
             str(work_test)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(work_dir),
        )
    except subprocess.TimeoutExpired:
        return False  # inconclusive — never silently counted as a kill
    if result.returncode == 0:
        return False
    m = _FAILED_SUMMARY.search(result.stdout)
    return bool(m and int(m.group(1)) >= 1)


def measure_mutation(
    test_file: Path,
    source_dir: Path,
    entry_rel: str,
    max_mutants: int = MAX_MUTANTS_PER_SAMPLE,
    timeout_per_mutant: float = 60.0,
) -> dict:
    """
    Mutation score of the generated suite against bounded AST mutants of
    the sample source.

    Optimization (evaluation-layer only): the mutant workspace is copied
    once per sample; between mutants only the mutated entry file is
    rewritten. Same operators, same cap, same killed/total semantics.
    """
    original = (Path(source_dir) / entry_rel).read_text(encoding="utf-8")
    mutants = generate_mutants(original, max_mutants=max_mutants)

    if not mutants:
        return {
            "mutants_total": 0,
            "mutants_killed": 0,
            "mutation_score": None,
            "mutant_details": [],
        }

    import tempfile
    killed = 0
    details = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        work_dir = Path(tmp) / "source"
        shutil.copytree(source_dir, work_dir)
        shutil.copy(test_file, work_dir / Path(test_file).name)
        for mutant in mutants:
            is_killed = _suite_kills_prepared(
                test_file, mutant["source"], entry_rel, work_dir, timeout_per_mutant,
            )
            killed += int(is_killed)
            details.append({"kind": mutant["kind"], "line": mutant["line"], "killed": is_killed})

    return {
        "mutants_total": len(mutants),
        "mutants_killed": killed,
        "mutation_score": round(killed / len(mutants), 4),
        "mutant_details": details,
    }
