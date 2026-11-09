"""
Test suite for agents/executor.py — Day 4 implementation.

Target: >90% coverage of executor.py
Strategy: Mock E2B sandbox, test all parsing edge cases, verify state updates.
"""

import logging
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from agents.executor import (
    ParsedTestResults,
    SandboxManager,
    UploadManifest,
    executor_node,
    parse_pytest_output,
    run_tests_locally,
    save_execution_log,
)
from core.state import AgentState, DebugReport, ExecutionResults


# ============================================================================
# Test parse_pytest_output() — Core parsing logic
# ============================================================================


def test_parse_pytest_output_happy_path():
    """Case 1: Happy path — all tests pass."""
    stdout = """
test_sample.py::test_foo PASSED
test_sample.py::test_bar PASSED

37 passed in 2.5s
TOTAL   100    15   85%
"""
    stderr = ""
    exit_code = 0

    result = parse_pytest_output(stdout, stderr, exit_code)

    assert result["total_tests"] == 37
    assert result["passed"] == 37
    assert result["failed"] == 0
    assert result["errors"] == 0
    assert result["skipped"] == 0
    assert result["coverage_percent"] == 85.0
    assert result["exit_code"] == 0
    assert result["execution_succeeded"] is True
    assert result["failed_test_names"] == []


def test_parse_pytest_output_mixed_results():
    """Case 2: Mixed results — passed, failed, errors."""
    stdout = """
test_sample.py::test_foo PASSED

FAILED test_sample.py::test_bar - AssertionError
FAILED test_other.py::test_qux - ValueError

35 passed, 2 failed, 1 error in 3.2s
TOTAL   200    40   80%
"""
    stderr = ""
    exit_code = 1

    result = parse_pytest_output(stdout, stderr, exit_code)

    assert result["total_tests"] == 38
    assert result["passed"] == 35
    assert result["failed"] == 2
    assert result["errors"] == 1
    assert result["skipped"] == 0
    assert result["coverage_percent"] == 80.0
    assert result["exit_code"] == 1
    assert result["execution_succeeded"] is False
    assert set(result["failed_test_names"]) == {"test_bar", "test_qux"}


def test_parse_pytest_output_with_skipped():
    """Case 3: Tests with skipped."""
    stdout = """
test_sample.py::test_foo PASSED
test_sample.py::test_bar SKIPPED

30 passed, 5 skipped in 2.1s
TOTAL   150    10   93%
"""
    stderr = ""
    exit_code = 0

    result = parse_pytest_output(stdout, stderr, exit_code)

    assert result["total_tests"] == 35
    assert result["passed"] == 30
    assert result["failed"] == 0
    assert result["errors"] == 0
    assert result["skipped"] == 5
    assert result["coverage_percent"] == 93.0
    assert result["execution_succeeded"] is True


def test_parse_pytest_output_ignores_warnings():
    """Case 4: Warnings are ignored, not counted as errors."""
    stdout = """
test_sample.py::test_foo PASSED

1 passed, 3 warnings in 1.5s
TOTAL   50    5   90%
"""
    stderr = ""
    exit_code = 0

    result = parse_pytest_output(stdout, stderr, exit_code)

    assert result["passed"] == 1
    assert result["failed"] == 0
    assert result["errors"] == 0
    assert result["skipped"] == 0
    assert result["execution_succeeded"] is True


def test_parse_pytest_output_coverage_extraction():
    """Case 5: Coverage parsing handles multiple formats."""
    test_cases = [
        ("TOTAL   100    15   85%", 85.0),
        ("TOTAL   100    15   50   85%", 85.0),
        ("Total coverage: 92%", 92.0),
        ("coverage: 78.5%", 78.5),
    ]

    for cov_line, expected in test_cases:
        stdout = f"""
test_sample.py::test_foo PASSED

1 passed in 1.0s
{cov_line}
"""
        result = parse_pytest_output(stdout, "", 0)
        assert result["coverage_percent"] == expected, f"Failed for: {cov_line}"


def test_parse_pytest_output_malformed_stdout():
    """Case 6: Malformed/empty stdout — never raises, returns safe defaults."""
    stdout = ""
    stderr = ""
    exit_code = 1

    result = parse_pytest_output(stdout, stderr, exit_code)

    assert result["total_tests"] == 0
    assert result["passed"] == 0
    assert result["failed"] == 0
    assert result["errors"] == 0
    assert result["coverage_percent"] == 0.0
    assert result["execution_succeeded"] is False


def test_parse_pytest_output_exit_code_authoritative():
    """Case 7: exit_code is authoritative — even with passing tests."""
    stdout = """
test_sample.py::test_foo PASSED

5 passed in 1.0s
TOTAL   50    0   100%
"""
    stderr = ""
    exit_code = 1  # Non-zero despite passing tests

    result = parse_pytest_output(stdout, stderr, exit_code)

    assert result["passed"] == 5
    assert result["execution_succeeded"] is False  # exit_code wins


def test_parse_pytest_output_ignores_xfailed_deselected():
    """Case 8: xfailed, xpassed, deselected are ignored."""
    stdout = """
test_sample.py::test_foo PASSED

1 passed, 2 xfailed, 1 xpassed, 3 deselected in 1.5s
TOTAL   50    5   90%
"""
    stderr = ""
    exit_code = 0

    result = parse_pytest_output(stdout, stderr, exit_code)

    assert result["passed"] == 1
    assert result["failed"] == 0


# ============================================================================
# Test run_tests_locally()
# ============================================================================


def test_run_tests_locally_no_test_files():
    """Case 8: No test files provided."""
    result = run_tests_locally([], [])

    assert result["total_tests"] == 0
    assert result["errors"] == 1
    assert result["execution_succeeded"] is False
    assert "No test files provided" in result["stderr"]


@patch("agents.executor.subprocess.run")
def test_run_tests_locally_uses_parse_pytest_output(mock_run):
    """Case 9: run_tests_locally uses parse_pytest_output (no duplication)."""
    mock_run.return_value = Mock(
        stdout="37 passed in 2.0s\nTOTAL   100   10   90%",
        stderr="",
        returncode=0,
    )

    result = run_tests_locally(["test_foo.py"], ["src.py"])

    assert isinstance(result, dict)
    assert result["passed"] == 37
    assert result["coverage_percent"] == 90.0
    assert result["execution_succeeded"] is True


@patch("agents.executor.subprocess.run")
def test_run_tests_locally_timeout(mock_run):
    """Case 10: Timeout handling."""
    mock_run.side_effect = subprocess.TimeoutExpired("pytest", 120)

    result = run_tests_locally(["test_foo.py"], [])

    assert result["errors"] == 1
    assert result["execution_succeeded"] is False
    assert "Timeout" in result["stderr"]


@patch("agents.executor.subprocess.run")
def test_run_tests_locally_exception(mock_run):
    """Case 11: Exception during execution."""
    mock_run.side_effect = Exception("Unexpected error")

    result = run_tests_locally(["test_foo.py"], [])

    assert result["errors"] == 1
    assert result["execution_succeeded"] is False
    assert "Unexpected error" in result["stderr"]


# ============================================================================
# Test save_execution_log()
# ============================================================================


def test_save_execution_log_creates_file(tmp_path, monkeypatch):
    """Case 10: save_execution_log creates file with correct content."""
    monkeypatch.chdir(tmp_path)

    results: ParsedTestResults = {
        "total_tests": 10,
        "passed": 8,
        "failed": 2,
        "errors": 0,
        "skipped": 0,
        "coverage_percent": 85.0,
        "failed_test_names": ["test_foo", "test_bar"],
        "stdout": "full stdout output",
        "stderr": "full stderr output",
        "exit_code": 1,
        "execution_succeeded": False,
    }

    save_execution_log("test_project", "e2b_sandbox", ["test_foo.py"], results)

    log_dir = tmp_path / "logs" / "executor"
    assert log_dir.exists()

    log_files = list(log_dir.glob("test_project_*.txt"))
    assert len(log_files) == 1

    content = log_files[0].read_text(encoding="utf-8")
    assert "test_project" in content
    assert "e2b_sandbox" in content
    assert "Total tests     : 10" in content
    assert "Passed          : 8" in content
    assert "Failed          : 2" in content
    assert "Coverage        : 85.0%" in content
    assert "['test_foo', 'test_bar']" in content
    assert "full stdout output" in content
    assert "full stderr output" in content


# ============================================================================
# Test SandboxManager
# ============================================================================


def test_sandbox_manager_init_missing_api_key(monkeypatch):
    """Case 11: SandboxManager raises ValueError if E2B_API_KEY missing."""
    monkeypatch.delenv("E2B_API_KEY", raising=False)

    with pytest.raises(ValueError, match="Missing E2B_API_KEY"):
        SandboxManager()


def test_sandbox_manager_init_success(monkeypatch):
    """Case 12: SandboxManager initializes with valid API key."""
    monkeypatch.setenv("E2B_API_KEY", "test_key_12345")

    manager = SandboxManager()
    assert manager.api_key == "test_key_12345"


def test_sandbox_manager_get_sandbox_path(monkeypatch, tmp_path):
    """Case 13: _get_sandbox_path preserves relative structure."""
    monkeypatch.setenv("E2B_API_KEY", "test_key")
    monkeypatch.chdir(tmp_path)

    # Create actual directory structure
    (tmp_path / "tests" / "generated").mkdir(parents=True)
    test_file = tmp_path / "tests" / "generated" / "test_foo.py"
    test_file.write_text("# test")

    manager = SandboxManager()

    # Relative path
    result = manager._get_sandbox_path(str(test_file))
    assert result == "/home/user/tests/generated/test_foo.py"


def test_sandbox_manager_upload_files(monkeypatch, tmp_path):
    """Case 14: upload_files preserves directory hierarchy."""
    monkeypatch.setenv("E2B_API_KEY", "test_key")
    monkeypatch.chdir(tmp_path)

    # Create test files
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    src_file = tmp_path / "src" / "module.py"
    test_file = tmp_path / "tests" / "test_module.py"
    src_file.write_text("def foo(): pass")
    test_file.write_text("def test_foo(): pass")

    manager = SandboxManager()

    mock_sandbox = MagicMock()
    mock_sandbox.files.write = MagicMock()
    mock_sandbox.run_code = MagicMock()

    manifests = manager.upload_files(
        mock_sandbox,
        [str(src_file)],
        [str(test_file)],
    )

    assert len(manifests) == 2
    assert manifests[0]["sandbox_path"] == "/home/user/src/module.py"
    assert manifests[1]["sandbox_path"] == "/home/user/tests/test_module.py"

    # Verify make_dir was called for each file's parent directory
    assert mock_sandbox.files.make_dir.call_count == 2
    # Verify files were written
    assert mock_sandbox.files.write.call_count == 2


def test_sandbox_manager_install_dependencies_with_requirements(
    monkeypatch, tmp_path
):
    """Case 15: install_dependencies uses requirements.txt if exists."""
    monkeypatch.setenv("E2B_API_KEY", "test_key")

    # Create requirements.txt in tmp_path
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("pytest\npytest-cov\n")

    manager = SandboxManager()
    mock_sandbox = MagicMock()
    
    # Mock successful installation
    mock_result_core = MagicMock()
    mock_result_core.logs.stdout = ["core_install_exit_code: 0"]
    mock_result_core.logs.stderr = []
    
    mock_result_target = MagicMock()
    mock_result_target.logs.stdout = ["target_deps_exit_code: 0"]
    mock_result_target.logs.stderr = []
    
    mock_sandbox.run_code.side_effect = [mock_result_core, mock_result_target]

    # Pass base_dir so it finds requirements.txt
    manager.install_dependencies(mock_sandbox, base_dir=str(tmp_path))

    # Verify requirements.txt was written to sandbox
    mock_sandbox.files.write.assert_called_once()
    call_args = mock_sandbox.files.write.call_args
    assert call_args[0][0] == "/home/user/target_requirements.txt"

    # Verify pip install was called twice (core + target)
    assert mock_sandbox.run_code.call_count == 2


def test_sandbox_manager_install_dependencies_minimal(monkeypatch, tmp_path):
    """Case 16: install_dependencies installs minimal packages without requirements.txt."""
    monkeypatch.setenv("E2B_API_KEY", "test_key")
    monkeypatch.chdir(tmp_path)

    manager = SandboxManager()
    mock_sandbox = MagicMock()
    
    # Mock successful core installation
    mock_result = MagicMock()
    mock_result.logs.stdout = ["core_install_exit_code: 0"]
    mock_result.logs.stderr = []
    mock_sandbox.run_code.return_value = mock_result

    manager.install_dependencies(mock_sandbox)

    # Verify minimal packages installed (only core, no target requirements)
    mock_sandbox.run_code.assert_called_once()
    call_cmd = mock_sandbox.run_code.call_args[0][0]
    assert "'pip', 'install'" in call_cmd
    assert "'pytest'" in call_cmd
    assert "'pytest-cov'" in call_cmd


def test_sandbox_manager_run_pytest_suite(monkeypatch, tmp_path):
    """Case 17: run_pytest_suite executes pytest and extracts results."""
    monkeypatch.setenv("E2B_API_KEY", "test_key")
    monkeypatch.chdir(tmp_path)

    manager = SandboxManager()

    mock_result = MagicMock()
    mock_result.logs.stdout = ["EXIT_CODE: 0", "37 passed", "TOTAL   100   10   90%"]
    mock_result.logs.stderr = []

    mock_sandbox = MagicMock()
    mock_sandbox.run_code.return_value = mock_result

    stdout, stderr, exit_code = manager.run_pytest_suite(
        mock_sandbox, ["tests/test_foo.py"]
    )

    assert exit_code == 0
    assert "37 passed" in stdout
    assert stderr == ""


def test_sandbox_manager_extract_exit_code(monkeypatch):
    """Case 18: _extract_exit_code handles various formats."""
    monkeypatch.setenv("E2B_API_KEY", "test_key")
    manager = SandboxManager()

    # Valid exit code
    output = "Some output\nEXIT_CODE: 0\nMore output"
    assert manager._extract_exit_code(output) == 0

    # Non-zero exit code
    output = "EXIT_CODE: 1"
    assert manager._extract_exit_code(output) == 1

    # Missing exit code → defaults to 1
    output = "No exit code here"
    assert manager._extract_exit_code(output) == 1

    # Malformed exit code → defaults to 1
    output = "EXIT_CODE: not_a_number"
    assert manager._extract_exit_code(output) == 1


# ============================================================================
# Test executor_node()
# ============================================================================


def test_executor_node_no_test_files():
    """Case 12: executor_node fails when no test files in state."""
    state: AgentState = {
        "project_id": "test",
        "source_files": ["src.py"],
        "code_context": {
            "functions": [],
            "classes": [],
            "imports": [],
            "complexity": {},
            "dependency_graph": {},
        },
        "patterns_retrieved": [],
        "test_files": [],  # Empty
        "execution_results": {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "coverage_percent": 0.0,
            "stdout": "",
            "stderr": "",
        },
        "failed_tests": [],
        "debug_report": {"root_cause": "", "fix_applied": "", "iterations": 0, "resolved": False},
        "iteration_count": 0,
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
        },
        "status": "running",
    }

    result = executor_node(state)
    assert result["status"] == "failed"


def test_executor_node_e2b_unavailable_fallback(tmp_path, monkeypatch):
    """Case 13: executor_node falls back to local when E2B unavailable."""
    monkeypatch.chdir(tmp_path)
    
    # Create test file
    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.write_text("def test_foo(): assert True")

    with patch("agents.executor.run_tests_locally") as mock_local:
        mock_local.return_value = ParsedTestResults(
            total_tests=1,
            passed=1,
            failed=0,
            errors=0,
            skipped=0,
            coverage_percent=100.0,
            failed_test_names=[],
            stdout="1 passed",
            stderr="",
            exit_code=0,
            execution_succeeded=True,
        )

        state: AgentState = {
            "project_id": "test",
            "source_files": ["src.py"],
            "code_context": {
                "functions": [],
                "classes": [],
                "imports": [],
                "complexity": {},
                "dependency_graph": {},
            },
            "patterns_retrieved": [],
            "test_files": ["tests/test_foo.py"],
            "execution_results": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "coverage_percent": 0.0,
                "stdout": "",
                "stderr": "",
            },
            "failed_tests": [],
            "debug_report": {"root_cause": "", "fix_applied": "", "iterations": 0, "resolved": False},
            "iteration_count": 0,
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
            },
            "status": "running",
        }

        result = executor_node(state)

        assert result["status"] == "tests_executed"
        assert result["execution_results"]["passed"] == 1
        assert result["execution_results"]["total_tests"] == 1
        assert result["failed_tests"] == []


def test_executor_node_e2b_error_no_silent_fallback(tmp_path, monkeypatch):
    """Case 13b: with E2B_API_KEY configured, sandbox failures are fatal and
    surface the real error — the executor must NOT silently fall back to
    local pytest."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("E2B_API_KEY", "test_key_12345")

    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.write_text("def test_foo(): assert True")

    state: AgentState = {
        "project_id": "test",
        "source_files": ["src.py"],
        "code_context": {
            "functions": [],
            "classes": [],
            "imports": [],
            "complexity": {},
            "dependency_graph": {},
        },
        "patterns_retrieved": [],
        "test_files": [str(test_file)],
        "tests_generated_count": 1,
        "llm_api_calls": 0,
        "llm_retries": 0,
        "llm_prompt_tokens": 0,
        "llm_completion_tokens": 0,
        "llm_total_tokens": 0,
        "llm_success_rate": 0.0,
        "ast_validation_passed": True,
        "pytest_validation_passed": True,
        "functions_skipped_trivial": [],
        "functions_failed_generation": [],
        "execution_results": ExecutionResults(
            total_tests=0, passed=0, failed=0, errors=0, skipped=0,
            coverage_percent=0.0, duration_seconds=0.0, stdout="", stderr="",
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

    # The sandbox cannot be created (bad key / network) — must surface, not fall back
    with patch("agents.executor.run_tests_locally") as mock_local,          patch("e2b_code_interpreter.Sandbox.create", side_effect=RuntimeError("sandbox provider unreachable")):
        result = executor_node(state)

    assert result["status"] == "failed"
    assert "E2B execution failed" in (result.get("error") or "")
    assert "sandbox provider unreachable" in (result.get("error") or "")
    mock_local.assert_not_called()  # no silent local fallback


def test_executor_node_state_correctly_populated(tmp_path, monkeypatch):
    # Simulate the no-key development environment: without E2B_API_KEY the
    # executor falls back to local execution.
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    """Case 14: executor_node correctly populates state after execution."""
    
    # Force E2B to not be available by patching the import
    import sys
    with patch.dict(sys.modules, {'e2b_code_interpreter': None}):
        with patch("agents.executor.run_tests_locally") as mock_local:
            mock_local.return_value = ParsedTestResults(
                total_tests=7,
                passed=5,
                failed=2,
                errors=0,
                skipped=0,
                coverage_percent=90.0,
                failed_test_names=["test_foo"],
                stdout="5 passed, 2 failed\nTOTAL   100   10   90%\nFAILED test.py::test_foo",
                stderr="",
                exit_code=1,
                execution_succeeded=False,
            )

            state: AgentState = {
                "project_id": "test",
                "source_files": ["src.py"],
                "code_context": {
                    "functions": [],
                    "classes": [],
                    "imports": [],
                    "complexity": {},
                    "dependency_graph": {},
                },
                "patterns_retrieved": [],
                "test_files": ["tests/test_foo.py"],
                "execution_results": {
                    "total_tests": 0,
                    "passed": 0,
                    "failed": 0,
                    "errors": 0,
                    "coverage_percent": 0.0,
                    "stdout": "",
                    "stderr": "",
                },
                "failed_tests": [],
                "debug_report": {"root_cause": "", "fix_applied": "", "iterations": 0, "resolved": False},
                "iteration_count": 0,
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
                },
                "status": "running",
            }

            result = executor_node(state)

            # Verify all ExecutionResults fields populated
            assert result["execution_results"]["total_tests"] == 7
            assert result["execution_results"]["passed"] == 5
            assert result["execution_results"]["failed"] == 2
            assert result["execution_results"]["errors"] == 0
            assert result["execution_results"]["coverage_percent"] == 90.0
            assert "5 passed, 2 failed" in result["execution_results"]["stdout"]
            assert result["execution_results"]["stderr"] == ""

            # Verify failed_tests populated
            assert result["failed_tests"] == ["test_foo"]

            # Verify status updated
            assert result["status"] == "tests_executed"
