"""
Test suite for the Debugger Agent (agents/debugger.py).

Covers: should_debug routing, failure extraction, fix validation/application,
the DebuggerLLM diagnosis flow (with a mocked LLM service), and the
debugger_node state updates including debug_history.
"""

import ast
import pytest
from unittest.mock import MagicMock, patch

from agents.debugger import (
    DebuggerLLM,
    FailureInfo,
    apply_fix_safely,
    debugger_node,
    extract_failure_info,
    should_debug,
    validate_fixed_code,
    MAX_DEBUG_ITERATIONS,
)
from core.state import AgentState, DebugReport, ExecutionResults


# ============================================================================
# Helpers
# ============================================================================

def make_state(**overrides) -> AgentState:
    """Build a minimal valid AgentState for tests."""
    state: AgentState = {
        "project_id": "test",
        "source_files": [],
        "code_context": {"functions": [], "classes": [], "imports": [], "complexity": {}, "dependency_graph": {}},
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
    state.update(overrides)
    return state


def make_failure_info(test_name: str = "test_foo") -> FailureInfo:
    return FailureInfo(
        test_name=test_name,
        test_file="test_file.py",
        error_type="AssertionError",
        error_message="expected 2 got 3",
        traceback="E       assert 3 == 2",
        failing_test_source=f"def {test_name}():\n    assert add(1, 1) == 2",
    )


# ============================================================================
# should_debug() — routing logic
# ============================================================================

def test_should_debug_no_failures():
    state = make_state()
    assert should_debug(state) == "end"


def test_should_debug_with_failures():
    state = make_state(failed_tests=["test_a"], execution_results={
        "total_tests": 5, "passed": 4, "failed": 1, "errors": 0, "skipped": 0,
        "coverage_percent": 50.0, "duration_seconds": 1.0, "stdout": "", "stderr": "",
        "failed_test_names": ["test_a"],
    })
    assert should_debug(state) == "debugger"


def test_should_debug_max_iterations_reached():
    state = make_state(failed_tests=["test_a"], iteration_count=MAX_DEBUG_ITERATIONS)
    assert should_debug(state) == "end"


def test_should_debug_pipeline_failed():
    state = make_state(status="failed", failed_tests=["test_a"])
    assert should_debug(state) == "end"


# ============================================================================
# extract_failure_info()
# ============================================================================

def test_extract_failure_info_normal_failure(tmp_path):
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("def test_foo():\n    assert 1 == 2\n")

    stdout = (
        "_______________________________ test_foo _______________________________\n"
        "\n"
        "    def test_foo():\n"
        ">       assert 1 == 2\n"
        "E       assert 1 == 2\n"
        "========================= short test summary info =========================\n"
        "FAILED test_foo.py::test_foo - assert 1 == 2\n"
    )

    failure = extract_failure_info("test_foo", str(test_file), stdout, "")
    assert failure is not None
    assert failure.test_name == "test_foo"
    assert failure.error_type
    assert "def test_foo():" in failure.failing_test_source


def test_extract_failure_info_missing_test_file():
    result = extract_failure_info("test_foo", "does_not_exist.py", "____ test_foo ____\nE assert", "")
    assert result is None


# ============================================================================
# validate_fixed_code() / apply_fix_safely()
# ============================================================================

def test_validate_fixed_code_valid():
    assert validate_fixed_code("def test_foo():\n    assert True\n") is True


def test_validate_fixed_code_invalid():
    assert validate_fixed_code("def test_foo(:\n    assert True") is False


def test_apply_fix_safely_valid_fix(tmp_path):
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("def test_foo():\n    assert 1 == 2\n\ndef test_bar():\n    assert True\n")

    applied = apply_fix_safely(str(test_file), "test_foo", "def test_foo():\n    assert 1 == 1\n", str(tmp_path))
    assert applied is True

    content = test_file.read_text()
    assert "assert 1 == 1" in content
    assert "def test_bar():" in content  # other tests preserved

    ast.parse(content)  # whole file must remain valid


def test_apply_fix_safely_rejects_outside_test_dir(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    outside_file = tmp_path / "source" / "test_foo.py"
    outside_file.parent.mkdir()
    outside_file.write_text("def test_foo():\n    assert True\n")

    applied = apply_fix_safely(str(outside_file), "test_foo", "def test_foo():\n    pass\n", str(tests_dir))
    assert applied is False


def test_apply_fix_safely_rejects_invalid_code(tmp_path):
    test_file = tmp_path / "test_foo.py"
    original = "def test_foo():\n    assert True\n"
    test_file.write_text(original)

    applied = apply_fix_safely(str(test_file), "test_foo", "def test_foo(:\n    pass", str(tmp_path))
    assert applied is False
    assert test_file.read_text() == original  # original preserved


# ============================================================================
# DebuggerLLM diagnosis (mocked service)
# ============================================================================

VALID_XML = (
    "<debug_result>"
    "<root_cause>Off-by-one in assertion</root_cause>"
    "<fix_description>Corrected expected value</fix_description>"
    "<confidence>high</confidence>"
    "<fixed_code>def test_foo():\n    assert 1 == 1</fixed_code>"
    "</debug_result>"
)


def _mock_service(content: str = VALID_XML):
    from llm import LLMResponse
    service = MagicMock()
    service.complete.return_value = LLMResponse(
        content=content, prompt_tokens=10, completion_tokens=10,
    )
    return service


@patch("agents.debugger.get_llm_service")
def test_debugger_llm_diagnose_success(mock_get_service):
    mock_get_service.return_value = _mock_service()

    debugger = DebuggerLLM()
    result = debugger.diagnose_failure(make_failure_info())

    assert result is not None
    assert result.root_cause == "Off-by-one in assertion"
    assert result.confidence == "high"
    assert "assert 1 == 1" in result.fixed_code


@patch("agents.debugger.get_llm_service")
def test_debugger_llm_empty_response_returns_none(mock_get_service):
    from llm import LLMError
    service = MagicMock()
    service.complete.side_effect = LLMError("LLM returned an empty completion (no content)")
    mock_get_service.return_value = service

    debugger = DebuggerLLM()
    result = debugger.diagnose_failure(make_failure_info())
    assert result is None


@patch("agents.debugger.get_llm_service")
def test_debugger_llm_malformed_xml_returns_none(mock_get_service):
    mock_get_service.return_value = _mock_service("no xml here at all")

    debugger = DebuggerLLM()
    result = debugger.diagnose_failure(make_failure_info())
    assert result is None


@patch("agents.debugger.get_llm_service")
def test_debugger_llm_missing_field_returns_none(mock_get_service):
    broken_xml = "<debug_result><root_cause>something</root_cause></debug_result>"
    mock_get_service.return_value = _mock_service(broken_xml)

    debugger = DebuggerLLM()
    result = debugger.diagnose_failure(make_failure_info())
    assert result is None


# ============================================================================
# debugger_node() — state updates
# ============================================================================

@patch("agents.debugger.get_llm_service")
def test_debugger_node_applies_fix_and_records_history(mock_get_service, tmp_path):
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("def test_foo():\n    assert 1 == 2\n")

    mock_get_service.return_value = _mock_service(VALID_XML.replace(
        "assert 1 == 1", "assert 1 == 1  # fixed"
    ))

    state = make_state(
        failed_tests=["test_foo"],
        test_files=[str(test_file)],
        test_dir=str(tmp_path),
        execution_results=ExecutionResults(
            total_tests=1, passed=0, failed=1, errors=0, skipped=0,
            coverage_percent=0.0, duration_seconds=1.0,
            stdout="____ test_foo ____\nE       assert 1 == 2\n", stderr="",
            failed_test_names=["test_foo"],
        ),
    )

    result = debugger_node(state)

    assert result["status"] == "debugged"
    assert result["iteration_count"] == 1
    assert result["total_fixes_applied"] == 1
    assert len(result["debug_history"]) == 1
    entry = result["debug_history"][0]
    assert entry["test_name"] == "test_foo"
    assert entry["applied"] is True
    assert "assert 1 == 1" in test_file.read_text()


@patch("agents.debugger.get_llm_service")
def test_debugger_node_no_failures_skips(mock_get_service):
    state = make_state()
    result = debugger_node(state)
    assert result["iteration_count"] == 0
    assert result["status"] == "running"


@patch("agents.debugger.get_llm_service")
def test_debugger_node_stops_at_max_iterations(mock_get_service):
    state = make_state(
        failed_tests=["test_foo"],
        iteration_count=MAX_DEBUG_ITERATIONS,
    )
    result = debugger_node(state)
    assert result["status"] == "failed"


# ============================================================================
# LLM service — fixed models + permanent-error policy (401/402/403 never retried)
# ============================================================================

from llm import LLMError, LLMResponse
from llm.service import OpenRouterService, get_llm_service


def _status_error(status_code: int, message: str) -> Exception:
    exc = Exception(message)
    exc.status_code = status_code
    return exc


def test_classify_401_is_permanent():
    kind, _ = OpenRouterService._classify(_status_error(401, "Invalid API key"))
    assert kind == "permanent"


def test_classify_402_is_permanent_even_in_flight_budget():
    """402 in-flight budget errors are NOT retried (per fixed-model policy)."""
    exc = _status_error(402, "Error code: 402 - {'error': {'message': "
        "'This request would exceed your available credits given your current "
        "in-flight requests.', 'metadata': {'reason': "
        "'in_flight_budget_exhausted', 'headers': {'Retry-After': '120'}}}}")
    kind, _ = OpenRouterService._classify(exc)
    assert kind == "permanent"


def test_classify_403_is_permanent():
    kind, _ = OpenRouterService._classify(_status_error(403, "Forbidden"))
    assert kind == "permanent"


def test_classify_404_model_unavailable_is_permanent():
    kind, _ = OpenRouterService._classify(_status_error(404, "No endpoints found for this model."))
    assert kind == "permanent"


def test_classify_429_is_retryable_and_honors_retry_after():
    exc = _status_error(429, "Rate limited. {'headers': {'Retry-After': '30'}}")
    kind, retry_after = OpenRouterService._classify(exc)
    assert kind == "rate_limit"
    assert retry_after == 30


def test_get_llm_service_rejects_unknown_role():
    with pytest.raises(ValueError, match="Unknown LLM role"):
        get_llm_service("manager")


@patch("llm.service.OpenRouterService._extract")
def test_permanent_error_raises_immediately_without_retries(mock_extract, monkeypatch):
    """A 402 must surface as LLMError on the FIRST call — zero retries."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    service = OpenRouterService(role="test_writer")

    calls = {"n": 0}

    def fake_create(**kwargs):
        calls["n"] += 1
        raise _status_error(402, "Error code: 402 - Not enough credits.")

    service.client = MagicMock()
    service.client.chat.completions.create = fake_create

    import llm.service as svc
    monkeypatch.setattr(svc.time, "sleep", lambda s: None)

    with pytest.raises(LLMError, match="402"):
        service.complete(system_prompt="s", user_prompt="u")
    assert calls["n"] == 1  # never retried


@patch("llm.service.OpenRouterService._extract")
def test_roles_get_their_own_fixed_models(mock_extract, monkeypatch):
    """Each role binds exactly one model; no cross-wiring is possible."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_TEST_WRITER_MODEL", "cohere/north-mini-code:free")
    monkeypatch.setenv("OPENROUTER_DEBUGGER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

    import llm.service as svc
    monkeypatch.setattr(svc, "_services", {})  # isolate singletons

    writer = get_llm_service("test_writer")
    debugger = get_llm_service("debugger")

    assert writer.model == "cohere/north-mini-code:free"
    assert debugger.model == "nvidia/nemotron-3-super-120b-a12b:free"
    assert writer.role == "test_writer"
    assert debugger.role == "debugger"
    assert writer is not debugger
    # Same role returns the same singleton
    assert get_llm_service("test_writer") is writer




def test_diagnose_response_reports_structure_without_secrets(monkeypatch):
    """_diagnose_response exposes model/finish_reason/usage and never secrets."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-secret-key-123")
    service = OpenRouterService(role="test_writer")

    class _Msg(dict):
        pass

    fake = MagicMock()
    fake.model_dump.return_value = {
        "id": "gen-123",
        "model": "cohere/north-mini-code:free",
        "provider": "cohere-free",
        "choices": [{
            "finish_reason": "length",
            "native_finish_reason": "MAX_TOKENS",
            "message": {"role": "assistant", "content": ""},
        }],
        "usage": {"prompt_tokens": 500, "completion_tokens": 0, "total_tokens": 500},
        "metadata": {"reason": "in_flight_budget_exhausted"},
    }

    diag = service._diagnose_response(fake)

    assert "cohere/north-mini-code:free" in diag       # model visible
    assert "finish_reason" in diag and "length" in diag
    assert "provider" in diag and "cohere-free" in diag
    assert "in_flight_budget_exhausted" in diag        # provider metadata visible
    assert "completion_tokens" in diag
    assert "sk-or-secret-key-123" not in diag          # never the API key
