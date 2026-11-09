"""
Professional Results Display for Multi-Agent Testing Pipeline.

Provides clean, user-friendly output for production deployment.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


class ResultsDisplay:
    """Professional results formatting for end users."""
    
    @staticmethod
    def print_header(title: str, width: int = 70) -> None:
        """Print a formatted header."""
        print("\n" + "=" * width)
        print(f"  {title}")
        print("=" * width)
    
    @staticmethod
    def print_section(title: str, width: int = 70) -> None:
        """Print a section divider."""
        print("\n" + "-" * width)
        print(f"  {title}")
        print("-" * width)
    
    @staticmethod
    def print_metric(label: str, value: Any, status: str = "") -> None:
        """Print a metric with status indicator."""
        status_icon = {
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "info": "ℹ️",
            "": ""
        }.get(status, "")
        
        print(f"  {label:.<40} {value} {status_icon}")
    
    @staticmethod
    def print_progress_bar(current: int, total: int, width: int = 50) -> None:
        """Print a progress bar."""
        if total == 0:
            return
        
        percentage = (current / total) * 100
        filled = int((current / total) * width)
        bar = "█" * filled + "░" * (width - filled)
        
        print(f"  [{bar}] {percentage:.1f}% ({current}/{total})")
    
    @staticmethod
    def display_analyser_results(code_context: Dict[str, Any], files_count: Optional[int] = None) -> None:
        """Display analyser results in a user-friendly format."""
        ResultsDisplay.print_header("ANALYSER RESULTS")
        
        functions = code_context.get("functions", [])
        classes = code_context.get("classes", [])
        complexity = code_context.get("complexity", {})
        
        # Summary
        ResultsDisplay.print_section("Summary")
        if files_count is None:
            files_count = len(set(k.split("::")[0] for k in complexity.keys())) if complexity else 0
        ResultsDisplay.print_metric("Files Analyzed", f"{files_count} files" if files_count else "0 files")
        ResultsDisplay.print_metric("Functions Found", f"{len(functions)} functions")
        ResultsDisplay.print_metric("Classes Found", f"{len(classes)} classes")
        
        # Complexity analysis
        if complexity:
            avg_complexity = sum(complexity.values()) / len(complexity)
            risk_zones = [k for k, v in complexity.items() if v > 5]
            
            ResultsDisplay.print_section("Complexity Analysis")
            ResultsDisplay.print_metric("Average Complexity", f"{avg_complexity:.2f}")
            ResultsDisplay.print_metric("Risk Zones", f"{len(risk_zones)} functions", 
                                       "warning" if len(risk_zones) > 0 else "success")
            
            if risk_zones:
                print("\n  Functions requiring extra attention:")
                for zone in risk_zones[:5]:  # Show top 5
                    func_name = zone.split("::")[-1]
                    score = complexity[zone]
                    print(f"    • {func_name} (complexity: {score})")
    
    @staticmethod
    def display_test_writer_results(test_files: list, metrics: Dict[str, Any]) -> None:
        """Display test writer results."""
        ResultsDisplay.print_header("TEST GENERATION RESULTS")
        
        # Summary
        ResultsDisplay.print_section("Generation Summary")
        ResultsDisplay.print_metric("Test Files Created", f"{len(test_files)} files", "success")
        ResultsDisplay.print_metric("Total Tests Generated", f"{metrics.get('total_tests', 0)} tests")
        
        # LLM Performance
        ResultsDisplay.print_section("LLM Performance")
        ResultsDisplay.print_metric("API Calls", f"{metrics.get('api_calls', 0)} calls")
        ResultsDisplay.print_metric("Success Rate", f"{metrics.get('success_rate', 100):.1f}%", "success")
        ResultsDisplay.print_metric("Total Tokens", f"{metrics.get('total_tokens', 0):,} tokens")
        
        # Quality metrics
        if metrics.get('ast_validation'):
            ResultsDisplay.print_metric("AST Validation", "PASSED", "success")
        else:
            ResultsDisplay.print_metric("AST Validation", "FAILED", "error")
        if metrics.get('pytest_validation'):
            ResultsDisplay.print_metric("Pytest Validation", "PASSED", "success")
        else:
            ResultsDisplay.print_metric("Pytest Validation", "FAILED", "warning")
    
    @staticmethod
    def display_executor_results(execution_results: Dict[str, Any]) -> None:
        """Display executor results with visual progress."""
        ResultsDisplay.print_header("TEST EXECUTION RESULTS")
        
        total = execution_results.get("total_tests", 0)
        passed = execution_results.get("passed", 0)
        failed = execution_results.get("failed", 0)
        coverage = execution_results.get("coverage_percent", 0)
        failed_tests = execution_results.get("failed_test_names", [])
        
        # Test Results Summary
        ResultsDisplay.print_section("Test Results")
        print("\n  Pass Rate:")
        ResultsDisplay.print_progress_bar(passed, total)
        
        print(f"\n  {'Total Tests':.<40} {total}")
        print(f"  {'Passed':.<40} {passed} ✅")
        print(f"  {'Failed':.<40} {failed}", "❌" if failed > 0 else "✅")
        
        # Show failed test names
        if failed > 0 and failed_tests:
            print(f"\n  ❌ Failed Tests ({len(failed_tests)}):")
            for test_name in failed_tests[:10]:  # Show max 10
                print(f"    • {test_name}")
            if len(failed_tests) > 10:
                print(f"    ... and {len(failed_tests) - 10} more")
        elif failed > 0:
            print(f"\n  ⚠️  {failed} test(s) failed (names not available)")
        
        # Coverage
        print(f"\n  Code Coverage:")
        ResultsDisplay.print_progress_bar(int(coverage), 100)
        ResultsDisplay.print_metric("Coverage", f"{coverage:.1f}%", 
                                   "success" if coverage >= 80 else "warning")
        
        # Execution Environment
        ResultsDisplay.print_section("Execution Environment")
        ResultsDisplay.print_metric("Mode", execution_results.get("mode", "sandbox"))
        ResultsDisplay.print_metric("Duration", f"{execution_results.get('duration', 0):.1f}s")
        
        # Success status explanation
        errors = execution_results.get("errors", 0)
        succeeded = (failed == 0 and errors == 0 and total > 0)
        ResultsDisplay.print_section("Pipeline Status")
        if succeeded:
            ResultsDisplay.print_metric("Status", "ALL TESTS PASSED", "success")
        elif total == 0:
            status_text = f"NO TESTS COLLECTED ({errors} error(s))" if errors > 0 else "NO TESTS COLLECTED"
            ResultsDisplay.print_metric("Status", status_text, "error" if errors > 0 else "warning")
        elif failed > 0 or errors > 0:
            ResultsDisplay.print_metric("Status", f"PARTIAL SUCCESS ({passed}/{total} passed, {failed} failed, {errors} errors)", "warning")
            print("\n  💡 Pipeline will continue to DEBUGGER to fix failed tests...")
        else:
            ResultsDisplay.print_metric("Status", "EXECUTION FAILED", "error")
    
    @staticmethod
    def display_debugger_results(debug_report: Dict[str, Any], iteration: int) -> None:
        """Display debugger execution results."""
        ResultsDisplay.print_header("DEBUGGER RESULTS — FIX ATTEMPT")
        
        print(f"\n  Iteration: {iteration}/3")
        print(f"  Tests to Fix: {debug_report.get('tests_processed', 0)}")
        print(f"  Fixes Applied: {debug_report.get('fixes_applied', 0)}")
        print(f"  Status: {'✅ Fixes Applied' if debug_report.get('fixes_applied', 0) > 0 else '⚠️ No Fixes Applied'}")
        
        if debug_report.get("root_cause"):
            print(f"\n  Root Cause Identified:")
            print(f"    {debug_report['root_cause'][:200]}")
        
        if debug_report.get("fix_applied"):
            print(f"\n  Fix Applied:")
            print(f"    {debug_report['fix_applied'][:200]}")
        
        print(f"\n  {'Resolving':.<40} {debug_report.get('resolved', False)}")
        
        print("\n  🔄 Returning to EXECUTOR for re-test...\n")
    
    @staticmethod
    def display_quality_report(final_report: Dict[str, Any]) -> None:
        """Display final quality report as a dashboard."""
        ResultsDisplay.print_header("QUALITY REPORT DASHBOARD", 70)
        
        quality_score = final_report.get("quality_score", 0)
        coverage = final_report.get("coverage_percent", 0)
        passed = final_report.get("passed", 0)
        total = final_report.get("total_tests", 0)
        risk = final_report.get("risk_level", "unknown")
        
        # Quality Score Gauge
        print("\n  QUALITY SCORE")
        ResultsDisplay.print_progress_bar(int(quality_score), 100)
        
        score_grade = "A+" if quality_score >= 95 else "A" if quality_score >= 90 else \
                     "B+" if quality_score >= 85 else "B" if quality_score >= 80 else \
                     "C" if quality_score >= 70 else "D"
        
        print(f"\n  Grade: {score_grade}")
        
        # Risk Level
        risk_color = {"low": "✅ LOW", "medium": "⚠️ MEDIUM", "high": "❌ HIGH"}
        print(f"  Risk Level: {risk_color.get(risk, risk)}")
        
        # Metrics Grid
        ResultsDisplay.print_section("Key Metrics")
        print(f"\n  {'Metric':<25} {'Value':<20} {'Status':<15}")
        print("  " + "-" * 60)
        
        pass_rate = (passed / total * 100) if total > 0 else 0
        print(f"  {'Pass Rate':<25} {pass_rate:.1f}%{'':<14} {'✅' if pass_rate >= 90 else '⚠️' if pass_rate >= 70 else '❌'}")
        print(f"  {'Coverage':<25} {coverage:.1f}%{'':<14} {'✅' if coverage >= 80 else '⚠️'}")
        print(f"  {'Tests Passed':<25} {passed}/{total}{'':<13} {'✅' if passed == total else '⚠️'}")
        print(f"  {'Complexity':<25} {final_report.get('complexity_avg', 0):.1f}{'':<15} {'✅'}")
        
        # Recommendations
        recommendations = final_report.get("recommendations", [])
        if recommendations:
            ResultsDisplay.print_section("Recommendations")
            for i, rec in enumerate(recommendations[:5], 1):
                print(f"\n  {i}. {rec}")
        
        print("\n" + "=" * 70)
    
    @staticmethod
    def display_pipeline_summary(state: Dict[str, Any]) -> None:
        """Display complete pipeline summary."""
        ResultsDisplay.print_header("PIPELINE EXECUTION SUMMARY", 70)
        
        # Timeline
        print("\n  TIMELINE")
        print(f"  Project ID: {state.get('project_id', 'N/A')}")
        print(f"  Status: {state.get('status', 'unknown').upper()}")
        
        # Stage Results
        print("\n  STAGE RESULTS")
        stages = [
            ("Analyser", "✅" if state.get("code_context") else "❌"),
            ("Test Writer", "✅" if state.get("test_files") else "❌"),
            ("Executor", "✅" if state.get("execution_results") else "❌"),
            ("Debugger", "✅" if state.get("execution_results", {}).get("failed", -1) == 0 else "⚠️" if state.get("iteration_count", 0) > 0 else "—"),
            ("Reporter", "✅" if state.get("final_report") else "❌"),
        ]
        
        for stage, status in stages:
            print(f"  {stage:<20} {status}")
        
        # Debugger Loop Info
        iteration = state.get("iteration_count", 0)
        if iteration > 0:
            print(f"\n  DEBUGGER LOOP")
            print(f"  Iterations: {iteration}")
            failed_count = state.get('execution_results', {}).get('failed', -1)
            fixes_text = f"Applied across {iteration} iteration(s) — see debugger logs" if failed_count == 0 else state.get('total_fixes_applied', 0)
            print(f"  Fixes Applied: {fixes_text}")
            print(f"  Resolved: {'Yes ✅' if failed_count == 0 else 'No ⚠️'}")
        
        # Final Metrics
        if state.get("final_report"):
            report = state["final_report"]
            print("\n  FINAL METRICS")
            print(f"  Quality Score: {report.get('quality_score', 0):.2f}/100")
            print(f"  Coverage: {report.get('coverage_percent', 0):.1f}%")
            print(f"  Tests: {report.get('passed', 0)}/{report.get('total_tests', 0)} passed")
        
        # Success explanation
        exec_results = state.get("execution_results", {})
        failed = exec_results.get("failed", 0)
        errors = exec_results.get("errors", 0)
        total = exec_results.get("total_tests", 0)
        if failed == 0 and errors == 0 and total > 0:
            print("\n  ✅ PIPELINE STATUS: ALL TESTS PASSED")
        elif total == 0 and errors > 0:
            print(f"\n  ❌ PIPELINE STATUS: FAILED ({errors} COLLECTION/RUNTIME ERROR(S))")
        elif total == 0:
            print("\n  ⚠️  PIPELINE STATUS: NO TESTS COLLECTED / EXECUTED")
        elif state.get("iteration_count", 0) >= 3:
            print(f"\n  ⚠️  PIPELINE STATUS: COMPLETED WITH {failed} FAILURE(S) AND {errors} ERROR(S) (max iterations reached)")
        else:
            print(f"\n  ⚠️  PIPELINE STATUS: COMPLETED WITH {failed} FAILURE(S) AND {errors} ERROR(S)")
        
        print("\n" + "=" * 70 + "\n")
    
    @staticmethod
    def export_summary_json(state: Dict[str, Any], output_path: str) -> None:
        """Export summary as JSON for integration."""
        summary = {
            "timestamp": datetime.now().isoformat(),
            "project_id": state.get("project_id"),
            "status": state.get("status"),
            "quality_score": state.get("final_report", {}).get("quality_score"),
            "coverage": state.get("execution_results", {}).get("coverage_percent"),
            "tests_passed": state.get("execution_results", {}).get("passed"),
            "tests_total": state.get("execution_results", {}).get("total_tests"),
            "risk_level": state.get("final_report", {}).get("risk_level")
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n  📄 Summary exported to: {output_path}")


def display_final_results(state: Dict[str, Any]) -> None:
    """Main function to display all results."""
    
    # Ensure stdout handles unicode/emojis properly on Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
        
    # Suppress detailed logging during display
    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("e2b").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    
    # Display each stage
    if state.get("code_context"):
        files_cnt = len(state.get("source_files", [])) if state.get("source_files") else None
        ResultsDisplay.display_analyser_results(state["code_context"], files_count=files_cnt)
    
    if state.get("test_files"):
        metrics = {
            "total_tests": state.get("tests_generated_count", len(state.get("test_files", []))),
            "api_calls": state.get("llm_api_calls", 0),
            "success_rate": state.get("llm_success_rate", 100.0),
            "total_tokens": state.get("llm_total_tokens", 0),
            "ast_validation": state.get("ast_validation_passed", False),
            "pytest_validation": state.get("pytest_validation_passed", False)
        }
        ResultsDisplay.display_test_writer_results(state["test_files"], metrics)
    
    if state.get("execution_results"):
        ResultsDisplay.display_executor_results(state["execution_results"])
    
    # Show debugger results if it ran
    iteration = state.get("iteration_count", 0)
    if iteration > 0 and state.get("debug_report"):
        ResultsDisplay.display_debugger_results(state["debug_report"], iteration)
    
    if state.get("final_report"):
        ResultsDisplay.display_quality_report(state["final_report"])
    
    # Overall summary
    ResultsDisplay.display_pipeline_summary(state)
    
    # Export JSON summary
    ResultsDisplay.export_summary_json(state, "pipeline_summary.json")
