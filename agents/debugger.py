"""
Debugger Agent — autonomous repair of generated tests.

Responsibilities:
    - Extract failure information from Executor results
    - Diagnose test failures using the shared OpenRouter LLM service
    - Generate test-only fixes (NEVER modify source code)
    - Validate fixes with AST parsing
    - Safely apply fixes to generated test files
    - Record a full, observable debug history for the UI

Single Responsibility:
    This agent diagnoses and fixes GENERATED TESTS ONLY.
    It NEVER modifies production/source code.
    It NEVER executes tests — that is Executor's responsibility.
    Resolution is determined ONLY by Executor on the next iteration.
"""

import ast
import logging
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal, Optional

from core.state import AgentState, DebugReport
from llm import DISABLE_REASONING, LLMError, ROLE_DEBUGGER, get_llm_service
from utils.rag import get_rag_memory

logger = logging.getLogger(__name__)

# Maximum debug iterations to prevent infinite loops (hard pipeline guard)
MAX_DEBUG_ITERATIONS = 3
MAX_FAILURES_PER_ITERATION = 5


class FailureInfo:
    """Structured failure information extracted from pytest output."""

    def __init__(
        self,
        test_name: str,
        test_file: str,
        error_type: str,
        error_message: str,
        traceback: str,
        failing_test_source: str,
    ) -> None:
        self.test_name = test_name
        self.test_file = test_file
        self.error_type = error_type
        self.error_message = error_message
        self.traceback = traceback
        self.failing_test_source = failing_test_source


class DiagnosisResult:
    """LLM diagnosis output."""

    def __init__(
        self,
        root_cause: str,
        fix_description: str,
        confidence: Literal["high", "medium", "low"],
        fixed_code: str,
    ) -> None:
        self.root_cause = root_cause
        self.fix_description = fix_description
        self.confidence = confidence
        self.fixed_code = fixed_code


class DebuggerLLM:
    """
    LLM-powered debugger for generated pytest failures.
    Uses the shared OpenRouter service (Auto model) for root cause analysis.

    Temperature 0.1 for deterministic, reproducible repairs.
    """

    def __init__(self) -> None:
        try:
            self.service = get_llm_service(ROLE_DEBUGGER)
        except LLMError as e:
            raise ValueError(str(e)) from e
        logger.info("DebuggerLLM initialized — model: %s (OpenRouter)", self.service.model)

    def diagnose_failure(
        self,
        failure: FailureInfo,
        source_context: Optional[str] = None
    ) -> Optional[DiagnosisResult]:
        """
        Diagnose a failing test and propose a test-only fix.

        Returns DiagnosisResult if diagnosis succeeds, None otherwise
        (bounded internal retries; never loops indefinitely).
        """
        prompt = self._build_diagnosis_prompt(failure, source_context)

        system_prompt = (
            "You are an expert Python test debugger. "
            "Your job is to diagnose failing pytest tests and propose fixes. "
            "CRITICAL RULES:\n"
            "1. You may ONLY modify the GENERATED TEST code\n"
            "2. You MUST NEVER modify production/source code\n"
            "3. Return your response in this exact XML format:\n"
            "<debug_result>\n"
            "  <root_cause>explanation</root_cause>\n"
            "  <fix_description>description</fix_description>\n"
            "  <confidence>high|medium|low</confidence>\n"
            "  <fixed_code>complete corrected test code</fixed_code>\n"
            "</debug_result>"
        )

        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                response = self.service.complete(
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    temperature=0.1,
                    max_tokens=2048,
                    extra_body=DISABLE_REASONING,
                )
            except LLMError as e:
                logger.warning("LLM diagnosis error (attempt %d/%d): %s", attempt, max_attempts, e)
                if attempt < max_attempts:
                    time.sleep(3)
                    continue
                return None

            parsed = self._parse_diagnosis(response.content)
            if parsed:
                logger.info("LLM diagnosis completed")
                return parsed

            # Observability: keep the raw response so unparseable diagnoses
            # can be inspected afterwards (same convention as the Test Writer).
            log_dir = Path("logs/raw_llm")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"debug_{failure.test_name}_attempt{attempt}.txt"
            try:
                log_path.write_text(response.content, encoding="utf-8")
            except OSError:
                pass

            logger.warning("Unparseable diagnosis on attempt %d/%d (saved to %s)",
                           attempt, max_attempts, log_path)
            if attempt < max_attempts:
                time.sleep(2)

        logger.info("Diagnosis failed after bounded attempts — continuing without fix")
        return None

    def _build_diagnosis_prompt(
        self,
        failure: FailureInfo,
        source_context: Optional[str]
    ) -> str:
        """Build diagnostic prompt for LLM."""
        prompt = f"""Diagnose and fix this failing pytest test.

FAILING TEST:
File: {failure.test_file}
Test: {failure.test_name}

ERROR:
Type: {failure.error_type}
Message: {failure.error_message}

TRACEBACK:
{failure.traceback}

CURRENT TEST CODE:
{failure.failing_test_source}
"""
        if source_context:
            prompt += f"\n\nSOURCE CODE CONTEXT:\n{source_context}\n"

        prompt += """
INSTRUCTIONS:
1. Identify the root cause of the failure
2. Propose a fix that modifies ONLY the test code
3. Do NOT modify source/production code
4. Do NOT weaken assertions to make tests pass
5. Do NOT delete the test
6. Return the complete corrected test function

Respond in the required XML format.
"""
        return prompt

    def _parse_diagnosis(self, xml_content: str) -> Optional[DiagnosisResult]:
        """Parse LLM XML response into a DiagnosisResult."""
        try:
            xml_match = re.search(r"<debug_result>.*?</debug_result>", xml_content, re.DOTALL)
            if not xml_match:
                logger.warning("No <debug_result> XML found in response")
                return None

            root = ET.fromstring(xml_match.group(0))

            root_cause_elem = root.find("root_cause")
            fix_desc_elem = root.find("fix_description")
            confidence_elem = root.find("confidence")
            fixed_code_elem = root.find("fixed_code")

            if any(elem is None for elem in [root_cause_elem, fix_desc_elem, confidence_elem, fixed_code_elem]):
                logger.warning("Missing required XML fields")
                return None

            root_cause = root_cause_elem.text or ""
            fix_description = fix_desc_elem.text or ""
            confidence_text = (confidence_elem.text or "low").lower().strip()
            fixed_code = fixed_code_elem.text or ""

            if confidence_text not in ("high", "medium", "low"):
                confidence_text = "low"

            if not fixed_code.strip():
                logger.warning("fixed_code is empty")
                return None

            return DiagnosisResult(
                root_cause=root_cause.strip(),
                fix_description=fix_description.strip(),
                confidence=confidence_text,  # type: ignore[arg-type]
                fixed_code=fixed_code.strip()
            )

        except ET.ParseError as e:
            logger.warning("XML parsing error: %s", e)
            return None
        except Exception as e:  # noqa: BLE001
            logger.warning("Unexpected parsing error: %s", e)
            return None


def extract_failure_info(
    test_name: str,
    test_file: str,
    stdout: str,
    stderr: str
) -> Optional[FailureInfo]:
    """
    Extract structured failure information from pytest output.

    Returns FailureInfo if extraction succeeds, None otherwise.
    """
    try:
        # Pytest failure section format: ____ test_name ____
        pattern = rf"__+ {re.escape(test_name)} __+\n(.*?)(?=__+|short test summary|$)"
        match = re.search(pattern, stdout, re.DOTALL)

        if not match:
            logger.warning("Could not find failure section for %s", test_name)
            return None

        failure_section = match.group(1).strip()

        error_match = re.search(r"([\w\.]+):\s*(.+?)(?:\n|$)", failure_section)
        if error_match:
            error_type = error_match.group(1)
            error_message = error_match.group(2).strip()
        else:
            error_type = "UnknownError"
            error_message = "Could not extract error message"

        test_path = Path(test_file)
        if not test_path.exists():
            logger.warning("Test file not found: %s", test_file)
            return None

        test_source = test_path.read_text(encoding="utf-8")

        func_pattern = rf"(def {re.escape(test_name)}\(.*?\):.*?)(?=\ndef\s+|\Z)"
        func_match = re.search(func_pattern, test_source, re.DOTALL)

        failing_test_source = func_match.group(1).strip() if func_match else test_source

        return FailureInfo(
            test_name=test_name,
            test_file=test_file,
            error_type=error_type,
            error_message=error_message,
            traceback=failure_section,
            failing_test_source=failing_test_source
        )

    except Exception as e:  # noqa: BLE001
        logger.error("Failure extraction error for %s: %s", test_name, e)
        return None


def validate_fixed_code(fixed_code: str) -> bool:
    """Validate fixed code using AST parsing."""
    try:
        ast.parse(fixed_code)
        logger.info("AST validation passed")
        return True
    except SyntaxError as e:
        logger.warning("AST validation failed: %s", e)
        return False


def apply_fix_safely(
    test_file: str,
    test_name: str,
    fixed_code: str,
    test_dir: str = "tests/generated"
) -> bool:
    """
    Safely apply a fix to a generated test file.

    SAFETY RULES:
    1. Only modify files inside test_dir
    2. Validate fixed_code with AST before writing
    3. Preserve original file if any validation fails
    """
    test_path = Path(test_file)
    test_dir_path = Path(test_dir).resolve()

    # SAFETY: verify this is a generated test file
    try:
        if not test_path.resolve().is_relative_to(test_dir_path):
            logger.error("REJECTED: %s is outside authorized %s", test_file, test_dir_path)
            return False
    except ValueError:
        logger.error("REJECTED: %s is outside authorized %s", test_file, test_dir_path)
        return False

    if not test_path.exists():
        logger.error("Test file not found: %s", test_file)
        return False

    if not validate_fixed_code(fixed_code):
        logger.error("Fixed code failed AST validation — original file preserved")
        return False

    try:
        original_content = test_path.read_text(encoding="utf-8")

        pattern = rf"(def {re.escape(test_name)}\(.*?\):.*?)(?=\ndef\s+|\Z)"

        if not re.search(pattern, original_content, re.DOTALL):
            logger.warning("Could not find function %s in %s", test_name, test_file)
            return False

        new_content = re.sub(
            pattern,
            lambda _m: fixed_code.rstrip() + "\n",
            original_content,
            count=1,
            flags=re.DOTALL
        )

        try:
            ast.parse(new_content)
        except SyntaxError as e:
            logger.error("Modified file failed AST validation: %s", e)
            return False

        test_path.write_text(new_content, encoding="utf-8")
        logger.info("Applied fix to %s in %s", test_name, test_file)
        return True

    except Exception as e:  # noqa: BLE001
        logger.error("Error applying fix: %s", e)
        return False


def debugger_node(state: AgentState) -> AgentState:
    """
    Debug failed tests and apply test-only fixes.

    Reads from state:
        - failed_tests, execution_results, test_files, iteration_count

    Writes to state:
        - debug_history: full observable trail of every diagnosis attempt
        - debug_report: aggregated diagnosis summary
        - iteration_count, total_fixes_applied, status
    """
    start_time = time.time()

    failed_tests = state.get("failed_tests", [])
    iteration = state.get("iteration_count", 0)

    logger.info("Debugger starting — iteration %d/%d", iteration + 1, MAX_DEBUG_ITERATIONS)

    if not failed_tests:
        logger.info("No failed tests — debugger skipped")
        return state

    if iteration >= MAX_DEBUG_ITERATIONS:
        logger.warning("Maximum debug iterations (%d) reached", MAX_DEBUG_ITERATIONS)
        state["status"] = "failed"
        return state

    logger.info("Processing %d failed test(s)", len(failed_tests))

    exec_results = state.get("execution_results", {})
    stdout = exec_results.get("stdout", "")
    stderr = exec_results.get("stderr", "")

    test_files = state.get("test_files", [])
    if not test_files:
        logger.error("No test files in state")
        state["status"] = "failed"
        return state

    try:
        debugger = DebuggerLLM()
    except ValueError as e:
        logger.error("Failed to initialize debugger: %s", e)
        state["status"] = "failed"
        state["error"] = str(e)
        return state

    debug_history = state.get("debug_history", [])
    fixes_applied = 0

    for test_name in failed_tests[:MAX_FAILURES_PER_ITERATION]:
        logger.info("Diagnosing %s...", test_name)

        # Find which test file contains this test
        test_file = None
        for tf in test_files:
            try:
                content = Path(tf).read_text(encoding="utf-8")
                if f"def {test_name}(" in content:
                    test_file = tf
                    break
            except Exception:
                continue

        if not test_file:
            logger.warning("Could not locate test file for %s", test_name)
            debug_history.append({
                "iteration": iteration + 1,
                "test_name": test_name,
                "error_type": "Unknown",
                "root_cause": "Test function could not be located in generated files.",
                "fix_description": "",
                "confidence": "low",
                "applied": False,
            })
            continue

        failure = extract_failure_info(test_name, test_file, stdout, stderr)
        if not failure:
            logger.warning("Could not extract failure info for %s", test_name)
            debug_history.append({
                "iteration": iteration + 1,
                "test_name": test_name,
                "error_type": "Unknown",
                "root_cause": "Failure details could not be extracted from pytest output.",
                "fix_description": "",
                "confidence": "low",
                "applied": False,
            })
            continue

        diagnosis = debugger.diagnose_failure(failure)
        if not diagnosis:
            logger.warning("LLM diagnosis failed for %s — skipping to next test", test_name)
            debug_history.append({
                "iteration": iteration + 1,
                "test_name": test_name,
                "error_type": failure.error_type,
                "root_cause": "LLM diagnosis unavailable for this failure.",
                "fix_description": "",
                "confidence": "low",
                "applied": False,
            })
            continue

        logger.info("Root cause: %s...", diagnosis.root_cause[:100])
        logger.info("Confidence: %s", diagnosis.confidence)

        applied = apply_fix_safely(
            test_file, test_name, diagnosis.fixed_code,
            state.get("test_dir", "tests/generated"),
        )

        debug_history.append({
            "iteration": iteration + 1,
            "test_name": test_name,
            "error_type": failure.error_type,
            "root_cause": diagnosis.root_cause,
            "fix_description": diagnosis.fix_description,
            "confidence": diagnosis.confidence,
            "applied": applied,
        })

        if applied:
            fixes_applied += 1

            # Store pattern in RAG memory for future test generation
            function_name = test_name.replace("test_", "").replace("_", " ").title().replace(" ", "")
            if not function_name:
                function_name = test_name

            rag_memory = get_rag_memory()
            rag_memory.store_pattern(
                function_name=function_name,
                function_signature=f"def {function_name}(...)",
                error_type=failure.error_type,
                root_cause=diagnosis.root_cause,
                fix_applied=diagnosis.fix_description,
                complexity=0.0
            )
            logger.info("Stored bug pattern for %s in RAG memory", function_name)
        else:
            logger.warning("Failed to apply fix for %s", test_name)

    # Update state
    state["debug_history"] = debug_history
    state["iteration_count"] = iteration + 1
    state["total_fixes_applied"] = state.get("total_fixes_applied", 0) + fixes_applied

    applied_entries = [d for d in debug_history if d.get("applied")]
    state["debug_report"] = DebugReport(
        root_cause="; ".join(d["root_cause"][:120] for d in applied_entries) if applied_entries else "No successful diagnosis this iteration",
        fix_applied=f"{fixes_applied} fix(es) applied" if fixes_applied > 0 else "No fixes applied",
        iterations=iteration + 1,
        resolved=False  # Only Executor can determine actual resolution
    )
    state["status"] = "debugged"

    elapsed = time.time() - start_time

    logger.info("=" * 60)
    logger.info("DEBUGGER RESULTS — iteration %d/%d", iteration + 1, MAX_DEBUG_ITERATIONS)
    logger.info("Failed tests      : %d", len(failed_tests))
    logger.info("Fixes applied     : %d", fixes_applied)
    logger.info("Execution time    : %.1fs", elapsed)
    logger.info("=" * 60)

    return state


def should_debug(state: AgentState) -> Literal["debugger", "end"]:
    """
    Routing function to determine whether to debug or end pipeline.

    This is NOT a LangGraph node — it is a conditional routing function.
    """
    failed_tests = state.get("failed_tests", [])
    failed_count = state.get("execution_results", {}).get("failed", 0)
    iteration = state.get("iteration_count", 0)
    status = state.get("status", "running")

    if status == "failed":
        logger.info("Pipeline failed — routing to END")
        return "end"

    has_failures = (failed_count > 0) or (len(failed_tests) > 0)

    if not has_failures:
        logger.info("No failed tests — routing to END")
        return "end"

    if iteration >= MAX_DEBUG_ITERATIONS:
        logger.info("Max iterations (%d) reached — routing to END", MAX_DEBUG_ITERATIONS)
        return "end"

    logger.info("Failed tests detected (count=%d) — routing to DEBUGGER", failed_count)
    return "debugger"
