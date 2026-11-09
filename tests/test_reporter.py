"""
Test suite for the Reporter Agent (agents/reporter.py).

Covers: quality scoring, risk assessment, code smell detection, technical
debt estimation, industry benchmarking, report generation with enriched
sections, and JSON/Markdown export.
"""

import json
from pathlib import Path

import pytest

from agents.reporter import (
    calculate_quality_score,
    assess_risk_level,
    detect_code_smells,
    calculate_technical_debt,
    benchmark_against_industry,
    generate_intelligent_recommendations,
    generate_report,
    export_report_json,
    export_report_markdown,
)
from core.state import AgentState, ExecutionResults, CodeContext, DebugReport


# ============================================================================
# Helpers
# ============================================================================

def make_state(**overrides) -> AgentState:
    state: AgentState = {
        "project_id": "test-project",
        "source_files": [],
        "code_context": CodeContext(
            functions=[], classes=[], imports=[], complexity={}, dependency_graph={},
        ),
        "analysis": {
            "files": [],
            "total_files": 0,
            "total_functions": 0,
            "total_classes": 0,
            "total_risk_zones": 0,
            "avg_complexity": 0.0,
            "top_risk_functions": [],
            "external_imports": [],
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
        "execution_results": ExecutionResults(
            total_tests=10, passed=10, failed=0, errors=0, skipped=0,
            coverage_percent=85.0, duration_seconds=5.0, stdout="", stderr="",
            failed_test_names=[],
        ),
        "failed_tests": [],
        "debug_report": DebugReport(root_cause="", fix_applied="", iterations=0, resolved=False),
        "debug_history": [],
        "iteration_count": 0,
        "total_fixes_applied": 0,
        "final_report": {},
        "error": "",
        "status": "running",
    }
    state.update(overrides)
    return state


# ============================================================================
# calculate_quality_score()
# ============================================================================

class TestQualityScore:
    def test_perfect_score(self):
        score = calculate_quality_score(pass_rate=100, coverage=100, complexity_avg=1, debug_iterations=0)
        assert score == 100.0

    def test_high_quality_score(self):
        score = calculate_quality_score(pass_rate=90, coverage=80, complexity_avg=5, debug_iterations=0)
        assert 75 <= score <= 100

    def test_low_quality_score(self):
        score = calculate_quality_score(pass_rate=20, coverage=10, complexity_avg=20, debug_iterations=3)
        assert score < 40

    def test_zero_pass_rate(self):
        score = calculate_quality_score(pass_rate=0, coverage=0, complexity_avg=10, debug_iterations=2)
        assert score >= 0

    def test_clamped_to_100(self):
        score = calculate_quality_score(pass_rate=100, coverage=100, complexity_avg=1, debug_iterations=0)
        assert score <= 100


# ============================================================================
# assess_risk_level()
# ============================================================================

class TestRiskLevel:
    def test_low_risk(self):
        assert assess_risk_level(quality_score=90, failed_tests=0, complexity_avg=4) == "low"

    def test_medium_risk(self):
        assert assess_risk_level(quality_score=70, failed_tests=2, complexity_avg=8) == "medium"

    def test_high_risk_low_quality(self):
        assert assess_risk_level(quality_score=40, failed_tests=2, complexity_avg=8) == "high"

    def test_high_risk_many_failures(self):
        assert assess_risk_level(quality_score=70, failed_tests=10, complexity_avg=8) == "high"


# ============================================================================
# detect_code_smells()
# ============================================================================

class TestCodeSmells:
    def test_no_smells_on_clean_code(self):
        context = CodeContext(
            functions=[{
                "name": "small_func", "args": "a, b", "return_type": "int",
                "docstring": "Does something.", "line_range": "1-5",
                "is_async": "False", "decorators": "[]",
            }],
            classes=[], imports=[], complexity={"small_func": 2}, dependency_graph={},
        )
        assert detect_code_smells(context) == []

    def test_detects_long_function(self):
        context = CodeContext(
            functions=[{
                "name": "huge_func", "args": "", "return_type": "None",
                "docstring": "Doc.", "line_range": "1-80",
                "is_async": "False", "decorators": "[]",
            }],
            classes=[], imports=[], complexity={}, dependency_graph={},
        )
        smells = detect_code_smells(context)
        assert any(s["type"] == "Long Function" for s in smells)

    def test_detects_high_complexity(self):
        context = CodeContext(
            functions=[{
                "name": "complex_func", "args": "", "return_type": "None",
                "docstring": "Doc.", "line_range": "1-30",
                "is_async": "False", "decorators": "[]",
            }],
            classes=[], imports=[], complexity={"complex_func": 18}, dependency_graph={},
        )
        smells = detect_code_smells(context)
        assert any(s["severity"] == "critical" for s in smells)

    def test_detects_missing_docstring(self):
        context = CodeContext(
            functions=[{
                "name": "public_func", "args": "", "return_type": "None",
                "docstring": "", "line_range": "1-10",
                "is_async": "False", "decorators": "[]",
            }],
            classes=[], imports=[], complexity={}, dependency_graph={},
        )
        smells = detect_code_smells(context)
        assert any(s["type"] == "Missing Documentation" for s in smells)


# ============================================================================
# generate_intelligent_recommendations()
# ============================================================================

class TestRecommendations:
    def test_low_coverage_recommends_improvement(self):
        debt = calculate_technical_debt([], 0, 40.0, 5.0)
        benchmark = benchmark_against_industry(70, 40.0, 5.0)
        maintenance = {"refactoring_urgency": 10, "monthly_maintenance_hours": 5, "monthly_maintenance_cost": 500}
        recs = generate_intelligent_recommendations([], debt, maintenance, benchmark, 100.0, 40.0)
        assert any(r["category"] == "Test Coverage" for r in recs)

    def test_critical_smell_is_priority_one(self):
        smells = [{
            "type": "Excessive Complexity", "severity": "critical", "location": "fn",
            "description": "d", "suggestion": "s", "impact": "i",
        }]
        debt = calculate_technical_debt(smells, 0, 90.0, 3.0)
        benchmark = benchmark_against_industry(85, 90.0, 3.0)
        maintenance = {"refactoring_urgency": 5, "monthly_maintenance_hours": 5, "monthly_maintenance_cost": 500}
        recs = generate_intelligent_recommendations(smells, debt, maintenance, benchmark, 100.0, 90.0)
        assert recs[0]["priority"] == 1
        assert "Critical Code Smell" in recs[0]["title"]

    def test_clean_project_has_no_recommendations(self):
        debt = {"debt_level": "low", "debt_hours": 0, "debt_cost": 0}
        benchmark = {"overall_percentile": 90, "benchmarks": []}
        maintenance = {"refactoring_urgency": 0, "monthly_maintenance_hours": 5, "monthly_maintenance_cost": 500}
        recs = generate_intelligent_recommendations([], debt, maintenance, benchmark, 100.0, 90.0)
        assert recs == []


# ============================================================================
# generate_report() — full node
# ============================================================================

class TestGenerateReport:
    def test_report_contains_enriched_sections(self):
        state = make_state(
            analysis={
                "files": [{"name": "a.py", "functions": 3, "classes": 1,
                           "risk_zones": 1, "avg_complexity": 4.0, "loc": 100}],
                "total_files": 1, "total_functions": 3, "total_classes": 1,
                "total_risk_zones": 1, "avg_complexity": 4.0,
                "top_risk_functions": [{"name": "fn", "file": "a.py", "complexity": 8}],
                "external_imports": ["requests"],
            },
            tests_generated_count=12,
            llm_api_calls=4,
            llm_total_tokens=8000,
        )
        result = generate_report(state)
        report = result["final_report"]

        assert report["total_tests"] == 10
        assert report["passed"] == 10
        assert report["failed"] == 0
        assert report["coverage_percent"] == 85.0
        assert report["analysis"]["total_files"] == 1
        assert report["generation"]["tests_generated"] == 12
        assert report["generation"]["llm_api_calls"] == 4
        assert report["debug_history"] == []
        assert report["risk_level"] in ("low", "medium", "high")
        assert result["status"] == "completed"

    def test_report_with_debug_history(self):
        history = [{
            "iteration": 1, "test_name": "test_add", "error_type": "AssertionError",
            "root_cause": "wrong expected value", "fix_description": "fixed it",
            "confidence": "high", "applied": True,
        }]
        state = make_state(debug_history=history, iteration_count=1, total_fixes_applied=1,
                           failed_tests=["test_add"],
                           execution_results=ExecutionResults(
                               total_tests=10, passed=9, failed=1, errors=0, skipped=0,
                               coverage_percent=80.0, duration_seconds=5.0, stdout="", stderr="",
                               failed_test_names=["test_add"],
                           ))
        result = generate_report(state)
        assert result["final_report"]["debug_history"] == history
        assert result["final_report"]["debug_iterations"] == 1


# ============================================================================
# Export functions
# ============================================================================

class TestExports:
    def _final_report(self):
        state = make_state()
        generate_report(state)
        return state["final_report"]

    def test_export_json(self, tmp_path):
        report = self._final_report()
        out = tmp_path / "report.json"
        export_report_json(report, out)

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["project_id"] == "test-project"
        assert "quality_score" in data

    def test_export_markdown(self, tmp_path):
        report = self._final_report()
        out = tmp_path / "report.md"
        export_report_markdown(report, out)

        content = out.read_text(encoding="utf-8")
        assert "Quality Analysis Report" in content
        assert "Quality Score" in content
