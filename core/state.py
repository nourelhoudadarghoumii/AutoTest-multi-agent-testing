"""
AgentState — Central state definition for the multi-agent testing pipeline.

This TypedDict flows through every node in the LangGraph StateGraph.
Each agent reads from and writes to specific fields, enabling a clean
data pipeline: Analyser → Test Writer → Executor ↔ Debugger → Reporter.
"""

from typing import TypedDict, Literal


class CodeContext(TypedDict):
    """Output of the Analyser agent — structured AST analysis."""
    functions: list[dict[str, str]]        # name, args, return_type, docstring
    classes: list[dict[str, str]]          # name, methods, bases
    imports: list[str]                      # imported modules (JSON strings)
    complexity: dict[str, int]             # file::function → cyclomatic complexity
    dependency_graph: dict[str, list[str]] # graph nodes/edges/critical modules


class AnalysisSummary(TypedDict):
    """Per-file and global analysis summary, consumed by the UI."""
    files: list[dict[str, object]]         # per-file: name, functions, classes, risk_zones, avg_complexity, loc
    total_files: int
    total_functions: int
    total_classes: int
    total_risk_zones: int
    avg_complexity: float
    top_risk_functions: list[dict[str, object]]
    external_imports: list[str]


class ExecutionResults(TypedDict):
    """Output of the Executor agent — pytest + coverage results."""
    total_tests: int
    passed: int
    failed: int
    errors: int
    skipped: int
    coverage_percent: float
    duration_seconds: float
    stdout: str
    stderr: str
    failed_test_names: list[str]


class DebugReport(TypedDict):
    """Aggregated debugger output."""
    root_cause: str
    fix_applied: str
    iterations: int
    resolved: bool


class FinalReport(TypedDict, total=False):
    """Output of the Reporter agent — aggregated quality report.

    Core metrics are always present; the observability sections
    (analysis / generation / debug_history) are embedded when available
    so the frontend can render them with real data only.
    """
    project_id: str
    summary: str
    quality_score: float
    coverage_percent: float
    total_tests: int
    passed: int
    failed: int
    skipped: int
    complexity_avg: float
    debug_iterations: int
    recommendations: list[dict[str, object]]
    risk_level: str

    # Enriched sections (real pipeline data, not estimates)
    analysis: dict[str, object]
    generation: dict[str, object]
    debug_history: list[dict[str, object]]
    test_files: list[str]

    # Heuristic insight sections (labeled as estimates in the UI)
    code_smells: list[dict[str, object]]
    technical_debt: dict[str, object]
    industry_benchmark: dict[str, object]
    maintenance_prediction: dict[str, object]
    ml_defect_hotspots: list[dict[str, object]]
    ml_test_effectiveness: dict[str, object]
    ml_velocity_impact: dict[str, object]
    ml_refactoring_priorities: list[dict[str, object]]


class AgentState(TypedDict):
    """
    Central state that flows through the entire LangGraph pipeline.

    Each field is owned by a specific agent:
        - project_id, source_files       → set at pipeline start
        - code_context, analysis         → written by Analyser
        - test_files                     → written by Test Writer
        - execution_results, failed_tests → written by Executor
        - debug_report, debug_history    → written by Debugger
        - final_report                   → written by Reporter
        - status, error                  → updated by each agent
    """
    project_id: str
    base_dir: str
    test_dir: str
    source_files: list[str]
    code_context: CodeContext
    analysis: AnalysisSummary
    patterns_retrieved: list[dict[str, str]]
    test_files: list[str]
    tests_generated_count: int
    llm_api_calls: int
    llm_retries: int
    llm_prompt_tokens: int
    llm_completion_tokens: int
    llm_total_tokens: int
    llm_success_rate: float
    ast_validation_passed: bool
    pytest_validation_passed: bool
    functions_skipped_trivial: list[str]
    functions_failed_generation: list[str]
    execution_results: ExecutionResults
    failed_tests: list[str]
    debug_report: DebugReport
    debug_history: list[dict[str, object]]
    iteration_count: int
    total_fixes_applied: int
    final_report: FinalReport
    error: str
    status: Literal[
        "running",
        "tests_generated",
        "tests_executed",
        "debugged",
        "completed",
        "failed"
    ]
