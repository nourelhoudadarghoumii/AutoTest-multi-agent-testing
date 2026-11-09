"""
LangGraph orchestration for the Multi-Agent Testing Pipeline.
"""

import os
import sys
import warnings
from pathlib import Path

# Suppress Pydantic V1 compatibility warning on Python 3.14+
warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality",
    category=UserWarning,
)

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END

from core.state import AgentState
from agents.analyser import analyser_node
from agents.test_writer import test_writer_node
from agents.executor import executor_node
from agents.debugger import debugger_node, should_debug
from agents.reporter import generate_report

def _validate_langsmith_config() -> bool:
    """Check if LangSmith is properly configured."""
    tracing_v2 = os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"
    smith_tracing = os.getenv("LANGSMITH_TRACING", "").lower() == "true"
    tracing_enabled = tracing_v2 or smith_tracing

    api_key = os.getenv("LANGSMITH_API_KEY", "")

    if not tracing_enabled:
        return False

    is_placeholder = (
        not api_key
        or api_key.startswith("lsv2_pt_xxxx")
        or api_key == "your-key-here"
        or len(api_key) < 20
    )

    if is_placeholder:
        print("[WARN] LangSmith tracing is enabled but API key is a placeholder.")
        print("       Disabling tracing to avoid 403 errors.")
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["LANGSMITH_TRACING"] = "false"
        return False

    if smith_tracing and not tracing_v2:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"

    langsmith_project = os.getenv("LANGSMITH_PROJECT", "").strip("\"'")
    langchain_project = os.getenv("LANGCHAIN_PROJECT", "").strip("\"'")
    if langsmith_project and not langchain_project:
        os.environ["LANGCHAIN_PROJECT"] = langsmith_project

    langsmith_endpoint = os.getenv("LANGSMITH_ENDPOINT", "").strip("\"'")
    langchain_endpoint = os.getenv("LANGCHAIN_ENDPOINT", "").strip("\"'")
    if langsmith_endpoint and not langchain_endpoint:
        os.environ["LANGCHAIN_ENDPOINT"] = langsmith_endpoint

    return True

def setup_environment() -> None:
    """Validate and configure environment variables."""
    load_dotenv()
    _validate_langsmith_config()

def build_graph() -> StateGraph:
    """Build and return the LangGraph for the pipeline."""
    graph = StateGraph(AgentState)
    graph.add_node("analyser", analyser_node)
    graph.add_node("test_writer", test_writer_node)
    graph.add_node("executor", executor_node)
    graph.add_node("debugger", debugger_node)
    graph.add_node("reporter", generate_report)

    graph.add_edge(START, "analyser")
    graph.add_edge("analyser", "test_writer")
    graph.add_edge("test_writer", "executor")

    # Conditional routing after execution:
    #   - pipeline failed (e.g. LLM unavailable)  → END (no bogus report)
    #   - failures remain and iterations remain   → debugger → executor
    #   - otherwise                               → reporter
    graph.add_conditional_edges(
        "executor",
        route_after_execution,
        {
            "debugger": "debugger",
            "report": "reporter",
            "fail": END,
        },
    )

    # Debugger always returns to executor for re-execution
    graph.add_edge("debugger", "executor")

    # Reporter is the final node on the success path
    graph.add_edge("reporter", END)

    return graph.compile()


def route_after_execution(state: AgentState) -> str:
    """Route after execution: debug, report, or fail out."""
    if state.get("status") == "failed":
        return "fail"
    return "debugger" if should_debug(state) == "debugger" else "report"

if __name__ == "__main__":
    import logging
    import sys
    
    # Configure logging to suppress verbose output
    logging.basicConfig(
        level=logging.WARNING,  # Only show warnings and errors
        format="%(levelname)s | %(name)s | %(message)s",
        stream=sys.stderr
    )
    
    # Suppress verbose third-party logging
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpx2").setLevel(logging.ERROR)
    logging.getLogger("e2b").setLevel(logging.ERROR)
    logging.getLogger("openai").setLevel(logging.ERROR)
    
    # Keep agent info logs
    logging.getLogger("agents.test_writer").setLevel(logging.INFO)
    logging.getLogger("agents.executor").setLevel(logging.INFO)
    logging.getLogger("agents.debugger").setLevel(logging.INFO)
    
    setup_environment()
    
    app = build_graph()
    
    import argparse
    from datetime import datetime
    
    parser = argparse.ArgumentParser(description="Run Multi-Agent Testing Pipeline")
    parser.add_argument("path", nargs="?", default="tests/sample_code", help="Path to a Python file or directory to test")
    args = parser.parse_args()
    
    target_path = Path(args.path)
    
    # 1. Dynamic Project ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if target_path.exists():
        project_name = target_path.name if target_path.name else "project"
    else:
        project_name = "unknown"
    
    # Preserve fallback behavior if running on default sample_code
    if args.path == "tests/sample_code":
        project_id = "hello-world-day2"
        base_dir = "tests/sample_code"
        test_dir = "tests/generated"
        source_files = [
            str(target_path / "sample_complex.py"),
            str(target_path / "sample_medium.py")
        ]
    else:
        project_id = f"{project_name}-{timestamp}"
        base_dir = str(target_path) if target_path.is_dir() else str(target_path.parent)
        test_dir = f"workspace/{project_id}/tests"
        source_files = []
        
        # 2. File Discovery (including __init__.py files for package structure)
        if target_path.is_file() and target_path.suffix == ".py":
            source_files.append(str(target_path))
            # Also include __init__.py from parent if it exists (for package context)
            parent_init = target_path.parent / "__init__.py"
            if parent_init.exists() and str(parent_init) not in source_files:
                source_files.append(str(parent_init))
        elif target_path.is_dir():
            excludes = {"venv", ".venv", "__pycache__", ".git", "tests", "site-packages", "dist", "build"}
            for root, dirs, files in os.walk(target_path):
                dirs[:] = [d for d in dirs if d not in excludes]
                for file in files:
                    # Include ALL .py files (including __init__.py)
                    if file.endswith(".py"):
                        source_files.append(str(Path(root) / file))

    initial_state = {
        "project_id": project_id,
        "base_dir": base_dir,
        "test_dir": test_dir,
        "source_files": source_files,
        "code_context": {
            "functions": [],
            "classes": [],
            "imports": [],
            "complexity": {},
            "dependency_graph": {}
        },
        "patterns_retrieved": [],
        "test_files": [],
        "tests_generated_count": 0,
        "llm_api_calls": 0,
        "llm_retries": 0,
        "llm_prompt_tokens": 0,
        "llm_completion_tokens": 0,
        "llm_total_tokens": 0,
        "llm_success_rate": 0.0,
        "ast_validation_passed": False,
        "pytest_validation_passed": False,
        "functions_skipped_trivial": [],
        "functions_failed_generation": [],
        "execution_results": {
            "total_tests": 0, "passed": 0, "failed": 0,
            "errors": 0, "coverage_percent": 0.0,
            "stdout": "", "stderr": "", "failed_test_names": []
        },
        "failed_tests": [],
        "debug_report": {"root_cause": "", "fix_applied": "", "iterations": 0, "resolved": False},
        "iteration_count": 0,
        "total_fixes_applied": 0,
        "final_report": {
            "project_id": "",
            "summary": "",
            "quality_score": 0.0,
            "coverage_percent": 0.0,
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "complexity_avg": 0.0,
            "debug_iterations": 0,
            "recommendations": [],
            "risk_level": "unknown"
        },
        "status": "running"
    }
    
    # Run pipeline
    final_state = app.invoke(initial_state)
    
    # Display professional results
    from utils.display import display_final_results
    display_final_results(final_state)
