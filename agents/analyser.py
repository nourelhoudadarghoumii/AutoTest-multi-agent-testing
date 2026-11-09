"""
Analyser Agent — Phase 1 of the testing pipeline.
"""
import ast
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, cast, TypedDict, List, Dict

import networkx as nx
from radon.complexity import cc_visit

from core.state import AgentState, AnalysisSummary, CodeContext

# Set up logging for lambdas
logger = logging.getLogger("analyser")
logger.setLevel(logging.WARNING)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(handler)

class FunctionInfo(TypedDict):
    """AST extracted function information."""
    name: str
    args: str
    return_type: str
    docstring: str
    line_range: str
    is_async: str
    decorators: str

class ClassInfo(TypedDict):
    """AST extracted class information."""
    name: str
    parents: str
    docstring: str
    methods: str
    line_range: str

class ImportInfo(TypedDict):
    """AST extracted import information."""
    module: str
    alias: str
    from_names: str
    is_stdlib: str

class FileStats(TypedDict):
    """Statistics calculated per file."""
    functions_count: int
    classes_count: int
    risk_zones: int
    score: float
    critical_modules: list[str]

class ASTParser(ast.NodeVisitor):
    """Parser to extract functions, classes, and imports from AST."""
    def __init__(self) -> None:
        """Initialize parser state."""
        self.functions: list[FunctionInfo] = []
        self.classes: list[ClassInfo] = []
        self.imports: list[ImportInfo] = []
        self.total_lines: int = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit standard function definitions."""
        self._handle_function(node, is_async=False)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definitions."""
        self._handle_function(node, is_async=True)
        self.generic_visit(node)

    def _handle_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
        """Extract generic function metadata."""
        args_list: list[str] = []
        
        # Positional args
        for a in getattr(node.args, "posonlyargs", []) + getattr(node.args, "args", []):
            arg_str = a.arg
            if getattr(a, "annotation", None):
                arg_str += f": {ast.unparse(a.annotation)}"
            args_list.append(arg_str)
            
        # Varargs
        if getattr(node.args, "vararg", None):
            arg_str = f"*{node.args.vararg.arg}"
            if getattr(node.args.vararg, "annotation", None):
                arg_str += f": {ast.unparse(node.args.vararg.annotation)}"
            args_list.append(arg_str)
            
        # Kwargs only
        for a in getattr(node.args, "kwonlyargs", []):
            arg_str = a.arg
            if getattr(a, "annotation", None):
                arg_str += f": {ast.unparse(a.annotation)}"
            args_list.append(arg_str)
            
        # Kwarg
        if getattr(node.args, "kwarg", None):
            arg_str = f"**{node.args.kwarg.arg}"
            if getattr(node.args.kwarg, "annotation", None):
                arg_str += f": {ast.unparse(node.args.kwarg.annotation)}"
            args_list.append(arg_str)

        returns = ast.unparse(node.returns) if getattr(node, "returns", None) else "Any"
        docstring = ast.get_docstring(node) or ""
        decorators = [ast.unparse(d) for d in node.decorator_list]
        
        func_info: FunctionInfo = {
            "name": node.name,
            "args": ", ".join(args_list),
            "return_type": returns,
            "docstring": docstring,
            "line_range": f"{node.lineno}-{node.end_lineno}",
            "is_async": "True" if is_async else "False",
            "decorators": json.dumps(decorators)
        }
        self.functions.append(func_info)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definitions."""
        docstring = ast.get_docstring(node) or ""
        bases = [ast.unparse(b) for b in node.bases]
        methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        
        cls_info: ClassInfo = {
            "name": node.name,
            "parents": ", ".join(bases),
            "docstring": docstring,
            "methods": ", ".join(methods),
            "line_range": f"{node.lineno}-{node.end_lineno}"
        }
        self.classes.append(cls_info)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Visit import statements."""
        for alias in node.names:
            is_stdlib = "True" if alias.name.split('.')[0] in sys.stdlib_module_names else "False"
            imp_info: ImportInfo = {
                "module": alias.name,
                "alias": alias.asname or "",
                "from_names": "",
                "is_stdlib": is_stdlib
            }
            self.imports.append(imp_info)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit from ... import statements."""
        module = node.module or ""
        is_stdlib = "True" if module.split('.')[0] in sys.stdlib_module_names else "False"
        from_names = [a.name for a in node.names]
        imp_info: ImportInfo = {
            "module": module,
            "alias": "",
            "from_names": ", ".join(from_names),
            "is_stdlib": is_stdlib
        }
        self.imports.append(imp_info)
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        """Visit lambda expressions, logging them as warnings."""
        logger.warning(f"Lambda found on line {node.lineno}")
        self.generic_visit(node)

def analyser_node(state: AgentState) -> AgentState:
    """Analyse source code and update state with metrics and graph."""
    start_time = time.time()
    
    global_dependency_graph = nx.DiGraph()
    all_functions: list[dict[str, str]] = []
    all_classes: list[dict[str, str]] = []
    all_imports: list[str] = []
    global_complexity: dict[str, int] = {}
    external_imports: list[str] = []

    file_stats: dict[str, FileStats] = {}
    source_files = state.get("source_files", [])
    
    for file_path_str in source_files:
        path = Path(file_path_str)
        if not path.exists():
            continue
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as f:
                source = f.read()
            
        total_lines = len(source.splitlines())
        
        try:
            tree = ast.parse(source, filename=path.name)
        except SyntaxError:
            continue
            
        parser = ASTParser()
        parser.visit(tree)
        parser.total_lines = total_lines
        
        all_functions.extend(cast(list[dict[str, str]], parser.functions))
        all_classes.extend(cast(list[dict[str, str]], parser.classes))
        for imp in parser.imports:
            all_imports.append(json.dumps(cast(dict[str, str], imp)))
            module_name = imp["module"]
            if module_name:
                global_dependency_graph.add_edge(path.name, module_name)
        
        # Radon Complexity
        blocks = cc_visit(source)
        file_complexities: dict[str, int] = {}
        
        def extract_complexities(block_list: Any, prefix: str = "") -> None:
            for b in block_list:
                b_type = type(b).__name__
                if b_type == "Function":
                    name = f"{prefix}{b.name}"
                    file_complexities[name] = int(b.complexity)
                    global_complexity[f"{path.name}::{name}"] = int(b.complexity)
                    if hasattr(b, "closures") and b.closures:
                        extract_complexities(b.closures, prefix=f"{name}.")
                elif b_type == "Class":
                    if hasattr(b, "methods") and b.methods:
                        extract_complexities(b.methods, prefix=f"{b.name}.")
                        
        extract_complexities(blocks)
                
        # Exclure les classes (radon les préfixe avec la classe parente)
        functions_only = {
            name: complexity 
            for name, complexity in file_complexities.items()
            if not any(
                cls_info["name"] == name 
                for cls_info in parser.classes
            )
        }

        risk_zones = sum(1 for c in functions_only.values() if c > 5)
        score = round(
            sum(functions_only.values()) / len(functions_only), 1
        ) if functions_only else 0.0

        file_stats[path.name] = {
            "functions_count": len(parser.functions),
            "classes_count": len(parser.classes),
            "risk_zones": risk_zones,
            "score": score,
            "loc": total_lines,
            "critical_modules": []
        }

        for imp in parser.imports:
            if imp["is_stdlib"] == "False" and imp["module"] and imp["module"] not in external_imports:
                external_imports.append(imp["module"])
        
    critical_modules = [str(n) for n in global_dependency_graph.nodes if global_dependency_graph.in_degree(n) > 1]
    
    for file_path_str in source_files:
        path = Path(file_path_str)
        if path.name in file_stats:
            imported_by_file = [str(v) for u, v in global_dependency_graph.edges if str(u) == path.name]
            file_stats[path.name]["critical_modules"] = [m for m in imported_by_file if m in critical_modules]
            
    dep_graph_dict: dict[str, list[str]] = {
        "nodes": [str(n) for n in global_dependency_graph.nodes],
        "edges": [f"{u}->{v}" for u, v in global_dependency_graph.edges],
        "critical_modules": critical_modules
    }
    
    code_context: CodeContext = {
        "functions": all_functions,
        "classes": all_classes,
        "imports": all_imports,
        "complexity": global_complexity,
        "dependency_graph": dep_graph_dict
    }
    state["code_context"] = code_context

    # ── Analysis summary consumed by the UI (real data only) ─────────────
    total_functions = sum(s["functions_count"] for s in file_stats.values())
    total_classes = sum(s["classes_count"] for s in file_stats.values())
    total_risk_zones = sum(s["risk_zones"] for s in file_stats.values())
    all_complexities = list(global_complexity.values())
    avg_complexity = round(sum(all_complexities) / len(all_complexities), 2) if all_complexities else 0.0

    top_risk = sorted(
        (
            {"name": key.split("::", 1)[-1], "file": key.split("::", 1)[0], "complexity": value}
            for key, value in global_complexity.items()
        ),
        key=lambda item: item["complexity"],
        reverse=True,
    )[:5]

    state["analysis"] = AnalysisSummary(
        files=[
            {
                "name": name,
                "functions": stats["functions_count"],
                "classes": stats["classes_count"],
                "risk_zones": stats["risk_zones"],
                "avg_complexity": stats["score"],
                "loc": stats["loc"],
            }
            for name, stats in file_stats.items()
        ],
        total_files=len(file_stats),
        total_functions=total_functions,
        total_classes=total_classes,
        total_risk_zones=total_risk_zones,
        avg_complexity=avg_complexity,
        top_risk_functions=top_risk,
        external_imports=external_imports,
    )
    state["status"] = "running"
    
    elapsed = time.time() - start_time
    
    print("=" * 60)
    print("ANALYSER RESULTS")
    print("=" * 60)
    
    total_functions = 0
    total_classes = 0
    total_risk_zones = 0
    
    for file_path_str in source_files:
        path = Path(file_path_str)
        if path.name not in file_stats:
            continue
        stats = file_stats[path.name]
        total_functions += stats["functions_count"]
        total_classes += stats["classes_count"]
        total_risk_zones += stats["risk_zones"]
        
        print(f"File: {path.name}")
        print(f"  Functions : {stats['functions_count']} | Classes : {stats['classes_count']} | Risk zones : {stats['risk_zones']} | Score : {stats['score']:.1f}")
        print(f"  Critical modules : {stats['critical_modules']}")
        print()
        
    print("-" * 60)
    print("TOTAL SUMMARY")
    print(f"  Files analysed  : {len(source_files)}")
    print(f"  Total functions : {total_functions}")
    print(f"  Total classes   : {total_classes}")
    print(f"  Total risk zones: {total_risk_zones}")
    print(f"  Pipeline time   : {elapsed:.1f}s")
    print("=" * 60)
    
    return state
