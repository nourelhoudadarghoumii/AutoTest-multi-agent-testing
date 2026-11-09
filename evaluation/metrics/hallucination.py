"""
Hallucination / invalid-API metric.

An "invalid API usage" is a name referenced by the generated test that is
NOT available to it — i.e. not defined/imported in the sample source, not a
Python builtin, not a pytest/stdlib testing name, and not a local name of
the test itself.
"""

import ast
import builtins
from pathlib import Path

# Names tests may legitimately use beyond the sample source
ALLOWED_TESTING_NAMES = {
    "pytest", "test", "assert", "monkeypatch", "capsys", "tmp_path",
    "parametrize", "mark", "raises", "approx", "fixture",
    "MagicMock", "patch", "mock", "Mock", "call", "ANY",
    "sys", "os", "json", "math", "re", "datetime", "unittest",
    "importorskip", "skip", "skipif", "xfail", "warns",
}


def _sample_defined_names(source_dir: Path, entry_rel: str) -> set[str]:
    """Top-level names defined or imported across the sample's entry file."""
    names: set[str] = set()
    for py in Path(source_dir).glob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    names.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    names.add(alias.asname or alias.name)
    return names


def _test_local_names(test_code: str) -> set[str]:
    """Names defined inside the test file (imports, defs, assignments)."""
    names: set[str] = set()
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.withitem) and node.optional_vars:
            if isinstance(node.optional_vars, ast.Name):
                names.add(node.optional_vars.id)
        elif isinstance(node, ast.comprehension):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
    return names


def measure_hallucination(
    test_code: str,
    source_dir: Path,
    entry_rel: str,
) -> dict:
    """
    Returns invalid-name usages and the hallucination rate:
        invalid_names / total_referenced_names
    """
    available = (
        _sample_defined_names(source_dir, entry_rel)
        | set(dir(builtins))
        | ALLOWED_TESTING_NAMES
        | _test_local_names(test_code)
        | {"self", "cls", "True", "False", "None", "__name__", "value", "key"}
    )

    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return {
            "total_name_references": 0,
            "invalid_names": [],
            "hallucination_rate": None,
            "note": "test code not parseable",
        }

    referenced: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            referenced.append(node.id)
        elif isinstance(node, ast.Attribute):
            # Attribute chains count via their root name only
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                referenced.append(root.id)

    # Dunder names (__file__, __name__, ...) are interpreter-provided and
    # appear in the generated import header — never hallucinations.
    invalid = sorted({
        name for name in referenced
        if name not in available and not (name.startswith("__") and name.endswith("__"))
    })

    return {
        "total_name_references": len(referenced),
        "invalid_names": invalid,
        "hallucination_rate": round(len(invalid) / len(referenced), 4) if referenced else None,
    }
