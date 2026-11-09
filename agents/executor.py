"""
Executor Agent — Phase 3 of the multi-agent testing pipeline.

Responsibilities:
    - Execute generated tests in an E2B Sandbox (local execution only as a
      development fallback when E2B_API_KEY is not configured; sandbox
      failures with a configured key are fatal and surface the real error)
    - Collect pytest stdout, stderr, exit code
    - Parse results into structured ExecutionResults
    - Update AgentState with results and failed test names

Single Responsibility:
    This agent is a pure execution engine.
    It never fixes, regenerates, or interprets test failures.
    All failure intelligence belongs to the Debugger.
"""

import logging
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, TypedDict

from core.state import AgentState, ExecutionResults

logger = logging.getLogger(__name__)


class ParsedTestResults(TypedDict):
    """Internal result of parse_pytest_output(). Never leaks to AgentState."""
    total_tests: int
    passed: int
    failed: int
    errors: int
    skipped: int
    coverage_percent: float
    failed_test_names: list[str]
    stdout: str
    stderr: str
    exit_code: int
    execution_succeeded: bool  # True ONLY when exit_code == 0


class UploadManifest(TypedDict):
    """Maps local file paths to sandbox paths after upload."""
    local_path: str
    sandbox_path: str


class SandboxManager:
    """
    Manages E2B sandbox lifecycle.
    Handles: validation, file upload, dependency install, execution.
    Single Responsibility: infrastructure only — no test logic.
    """

    SANDBOX_TIMEOUT: int = 600

    def __init__(self) -> None:
        """Verify E2B_API_KEY is set. Raise ValueError if missing."""
        self.api_key = os.getenv("E2B_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Missing E2B_API_KEY.\n"
                "Get your key at e2b.dev → Dashboard → API Keys"
            )
        logger.info("SandboxManager initialized")

    def _compute_common_root(self, all_files: list[str]) -> Path:
        """Finds common ancestor directory across all files and cwd."""
        valid_paths = [str(Path(f).resolve()) for f in all_files if Path(f).exists()]
        if not valid_paths:
            return Path.cwd().resolve()
        try:
            return Path(os.path.commonpath(valid_paths + [str(Path.cwd().resolve())]))
        except Exception:
            return Path.cwd().resolve()

    def _get_sandbox_path(self, local_path: str, common_root: Optional[Path] = None) -> str:
        """
        Converts a local path to its sandbox equivalent.
        Preserves relative project structure under /home/user/.
        """
        path = Path(local_path)
        if not path.is_absolute():
            path = Path.cwd() / path

        root = common_root or getattr(self, "_common_root", Path.cwd().resolve())
        try:
            rel = path.resolve().relative_to(root)
        except Exception:
            try:
                rel = path.resolve().relative_to(Path.cwd().resolve())
            except Exception:
                rel = Path(path.name)

        return f"/home/user/{rel.as_posix()}"

    def upload_files(
        self,
        sandbox,
        source_files: list[str],
        test_files: list[str]
    ) -> list[UploadManifest]:
        """
        Uploads all files preserving relative directory hierarchy.
        The entire project structure is reproduced inside the sandbox
        so that imports work exactly as locally.
        Never flattens the directory structure.
        Returns list of UploadManifest entries.
        """
        manifests: list[UploadManifest] = []
        all_files = source_files + test_files
        self._common_root = self._compute_common_root(all_files)

        for local_path in all_files:
            path = Path(local_path)
            if not path.exists():
                logger.warning(f"File not found, skipping: {local_path}")
                continue

            sandbox_path = self._get_sandbox_path(local_path, self._common_root)
            sandbox_dir = str(Path(sandbox_path).parent)

            # Create parent directories in sandbox using native files API
            sandbox.files.make_dir(sandbox_dir)

            content = path.read_text(encoding="utf-8")
            sandbox.files.write(sandbox_path, content)

            manifests.append(
                UploadManifest(
                    local_path=str(path),
                    sandbox_path=sandbox_path
                )
            )

        logger.info(f"Uploaded {len(manifests)} files to sandbox")
        return manifests

    def install_dependencies(self, sandbox, base_dir: str = "") -> None:
        """
        Installs test dependencies inside the E2B sandbox.
        1. Always ensures pytest, pytest-cov, pytest-asyncio are installed.
        2. If the target project has a requirements.txt, installs its dependencies.
        
        Raises:
            RuntimeError: If dependency installation fails
        """
        # Step 1: Install core test runner packages
        core_cmd = (
            "import subprocess\n"
            "r = subprocess.run(\n"
            "    ['pip', 'install', 'pytest', 'pytest-cov', 'pytest-asyncio',\n"
            "     '--quiet', '--no-warn-script-location'],\n"
            "    capture_output=True, text=True\n"
            ")\n"
            "print('core_install_exit_code:', r.returncode)\n"
            "if r.returncode != 0:\n"
            "    print('STDERR:', r.stderr)\n"
        )
        result = sandbox.run_code(core_cmd)
        output = "\n".join(result.logs.stdout or [])
        
        # Check if core packages installed successfully
        if "core_install_exit_code: 0" not in output:
            stderr = "\n".join(result.logs.stderr or [])
            error_msg = f"Failed to install core test dependencies (pytest, pytest-cov, pytest-asyncio).\nOutput: {output}\nError: {stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        logger.info("Core test runner packages installed in sandbox (pytest, pytest-cov, pytest-asyncio)")

        # Step 2: Discover target project requirements.txt (if any)
        req_paths = []
        if base_dir:
            curr = Path(base_dir).resolve()
            while curr != curr.parent:
                rf = curr / "requirements.txt"
                if rf.exists() and rf not in req_paths:
                    # Skip multi_agent_testing's own requirements
                    if "multi_agent_testing" not in str(rf):
                        req_paths.append(rf)
                curr = curr.parent

        if req_paths:
            combined_reqs = []
            for rp in req_paths:
                combined_reqs.append(rp.read_text(encoding="utf-8"))
            sandbox.files.write("/home/user/target_requirements.txt", "\n".join(combined_reqs))
            dep_cmd = (
                "import subprocess\n"
                "r = subprocess.run(\n"
                "    ['pip', 'install', '-r', '/home/user/target_requirements.txt',\n"
                "     '--quiet', '--no-warn-script-location'],\n"
                "    capture_output=True, text=True\n"
                ")\n"
                "print('target_deps_exit_code:', r.returncode)\n"
                "if r.returncode != 0:\n"
                "    print('STDERR:', r.stderr)\n"
            )
            result = sandbox.run_code(dep_cmd)
            output = "\n".join(result.logs.stdout or [])
            
            # Check if target dependencies installed successfully
            if "target_deps_exit_code: 0" not in output:
                stderr = "\n".join(result.logs.stderr or [])
                error_msg = f"Failed to install project dependencies from requirements.txt.\nFiles: {[str(p) for p in req_paths]}\nOutput: {output}\nError: {stderr}"
                logger.warning(error_msg)
                # Log warning but don't fail - project may work without external deps
                logger.warning("Continuing despite dependency installation warning - tests may fail if dependencies are required")
            else:
                logger.info(f"Target dependencies installed in sandbox from {len(req_paths)} requirements file(s)")

        logger.info("Dependency installation complete")

    def run_pytest_suite(
        self,
        sandbox,
        test_files: list[str],
        base_dir: str = "tests/sample_code"
    ) -> tuple[str, str, int]:
        """
        Runs the full test suite in ONE pytest execution.
        Produces one stdout, one stderr, one coverage report.
        Returns (stdout, stderr, exit_code).
        """
        sandbox_test_paths = [
            self._get_sandbox_path(tf, getattr(self, "_common_root", None)) for tf in test_files
        ]

        # Coverage target = sandbox path of the source directory being tested
        cov_target = self._get_sandbox_path(base_dir, getattr(self, "_common_root", None))

        cmd = (
            f"import subprocess\n"
            f"r = subprocess.run(\n"
            f"    ['python', '-m', 'pytest'] + {sandbox_test_paths} +\n"
            f"    ['-v', '--tb=short', '--no-header', '--continue-on-collection-errors',\n"
            f"     '--cov={cov_target}', '--cov-report=term-missing'],\n"
            f"    capture_output=True, text=True,\n"
            f"    cwd='/home/user'\n"
            f")\n"
            f"print('EXIT_CODE:', r.returncode)\n"
            f"print('STDOUT_START')\n"
            f"print(r.stdout)\n"
            f"print('STDOUT_END')\n"
            f"print('STDERR_START')\n"
            f"print(r.stderr)\n"
            f"print('STDERR_END')\n"
        )

        result = sandbox.run_code(cmd)
        raw_output = "\n".join(result.logs.stdout or [])
        raw_error = "\n".join(result.logs.stderr or [])
        exit_code = self._extract_exit_code(raw_output)
        
        # Parse stdout from sandbox output (contains EXIT_CODE line at start)
        # The pytest stdout is everything after EXIT_CODE line
        lines = raw_output.split("\n")
        
        # Find where EXIT_CODE line ends and real stdout begins
        stdout_lines = []
        found_exit_code = False
        for line in lines:
            if line.startswith("EXIT_CODE:"):
                found_exit_code = True
                continue
            if found_exit_code:
                stdout_lines.append(line)
        
        pure_stdout = "\n".join(stdout_lines)
        pure_stderr = raw_error

        return pure_stdout, pure_stderr, exit_code

    def _extract_exit_code(self, output: str) -> int:
        """Extracts EXIT_CODE from sandbox stdout. Defaults to 1 on failure."""
        for line in output.splitlines():
            if line.startswith("EXIT_CODE:"):
                try:
                    return int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
        return 1


def parse_pytest_output(
    stdout: str,
    stderr: str,
    exit_code: int
) -> ParsedTestResults:
    """
    Parses pytest -v --tb=short output into ParsedTestResults.
    Handles all standard pytest summary formats:
        37 passed
        37 passed, 2 skipped
        35 passed, 2 failed
        35 passed, 2 failed, 1 error
        35 passed, 2 failed, 1 error, 1 skipped

    Ignores: warnings, deselected, xfailed, xpassed.
    Only extracts: passed, failed, errors, skipped, coverage, failed names.

    Never raises. Always returns a valid ParsedTestResults.
    If parsing fails: passed=0, failed=0, errors=1, succeeded=False.

    exit_code is authoritative: execution_succeeded = (exit_code == 0).
    """
    passed = 0
    failed = 0
    errors = 0
    skipped = 0
    coverage_percent = 0.0
    failed_test_names: list[str] = []

    try:
        # Parse counts — ignore warnings, xfailed, xpassed, deselected
        count_map = {
            "passed": re.compile(r"(\d+)\s+passed"),
            "failed": re.compile(r"(\d+)\s+failed"),
            "errors": re.compile(r"(\d+)\s+error"),
            "skipped": re.compile(r"(\d+)\s+skipped"),
        }

        for line in stdout.splitlines():
            # Skip lines that are about warnings/xfail/deselected (but allow passed/failed counts)
            if any(k in line.lower() for k in ("warning", "xfailed", "xpassed", "deselected")):
                # Still parse if it contains actual test counts
                if not any(k in line for k in ("passed", "failed", "error", "skipped")):
                    continue

            # Parse test counts
            m = count_map["passed"].search(line)
            if m:
                passed = int(m.group(1))

            m = count_map["failed"].search(line)
            if m:
                failed = int(m.group(1))

            m = count_map["errors"].search(line)
            if m:
                errors = int(m.group(1))

            m = count_map["skipped"].search(line)
            if m:
                skipped = int(m.group(1))

        # Robust coverage parsing across pytest-cov versions
        cov_patterns = [
            re.compile(r"TOTAL\s+\d+\s+\d+\s+(\d+)%"),
            re.compile(r"TOTAL\s+\d+\s+\d+\s+\d+\s+(\d+)%"),
            re.compile(r"Total\s+coverage[:\s]+(\d+)%"),
            re.compile(r"coverage:\s+(\d+(?:\.\d+)?)%"),
        ]

        for pattern in cov_patterns:
            match = pattern.search(stdout)
            if match:
                coverage_percent = float(match.group(1))
                break

        # Parse failed test names from FAILED lines
        # Format: tests/generated/test_file.py::test_name FAILED
        failed_test_names = []
        for line in stdout.split('\n'):
            if 'FAILED' in line and '::' in line:
                # Extract test name after ::
                parts = line.split('::')
                if len(parts) >= 2:
                    test_name = parts[1].split()[0]
                    failed_test_names.append(test_name)

    except Exception as e:
        logger.warning(f"parse_pytest_output failed: {e} — returning safe defaults")
        return ParsedTestResults(
            total_tests=0, passed=0, failed=0, errors=1, skipped=0,
            coverage_percent=0.0, failed_test_names=[],
            stdout=stdout, stderr=stderr,
            exit_code=exit_code, execution_succeeded=False
        )

    return ParsedTestResults(
        total_tests=passed + failed + errors + skipped,
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
        coverage_percent=round(coverage_percent, 1),
        failed_test_names=failed_test_names,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        execution_succeeded=(exit_code == 0)
    )


def run_tests_locally(
    test_files: list[str],
    source_files: list[str],
    base_dir: str = "tests/sample_code"
) -> ParsedTestResults:
    """
    Fallback when E2B Sandbox is unavailable.
    Runs the full test suite in ONE subprocess call, executed from the
    project source directory so the project's own modules resolve
    correctly (and can never collide with AutoTest's internal packages).
    Uses parse_pytest_output() — no duplicated parsing logic.
    Returns same ParsedTestResults structure as sandbox execution.
    """
    logger.warning("E2B unavailable — local fallback (no sandbox isolation)")

    if not test_files:
        logger.error("No test files for local fallback")
        return ParsedTestResults(
            total_tests=0, passed=0, failed=0, errors=1, skipped=0,
            coverage_percent=0.0, failed_test_names=[],
            stdout="", stderr="No test files provided",
            exit_code=1, execution_succeeded=False
        )

    cov_target = str(Path(base_dir).resolve())

    try:
        result = subprocess.run(
            ["python", "-m", "pytest"] +
            [str(Path(f).resolve()) for f in test_files] +
            ["-v", "--tb=short", "--no-header", "--continue-on-collection-errors",
             f"--cov={cov_target}", "--cov-report=term-missing"],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=cov_target,
        )
        return parse_pytest_output(
            result.stdout, result.stderr, result.returncode
        )
    except subprocess.TimeoutExpired:
        logger.error("Local execution timed out after 600s")
        return ParsedTestResults(
            total_tests=0, passed=0, failed=0, errors=1, skipped=0,
            coverage_percent=0.0, failed_test_names=[],
            stdout="", stderr="Timeout after 600s",
            exit_code=1, execution_succeeded=False
        )
    except Exception as e:
        logger.exception(f"Local fallback failed: {e}")
        return ParsedTestResults(
            total_tests=0, passed=0, failed=0, errors=1, skipped=0,
            coverage_percent=0.0, failed_test_names=[],
            stdout="", stderr=str(e),
            exit_code=1, execution_succeeded=False
        )


def save_execution_log(
    project_id: str,
    execution_mode: str,
    test_files: list[str],
    results: ParsedTestResults
) -> None:
    """
    Saves execution output to logs/executor/{project_id}_{timestamp}.txt.
    Follows same observability philosophy as Test Writer (logs/prompts/, logs/raw_llm/).
    Content: summary + full stdout + full stderr.
    """
    log_dir = Path("logs/executor")
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"{project_id}_{timestamp}.txt"

    sep = "=" * 60
    content = "\n".join([
        sep,
        f"EXECUTOR LOG — {timestamp}",
        sep,
        f"Project ID      : {project_id}",
        f"Execution mode  : {execution_mode}",
        f"Test files      : {len(test_files)}",
        sep,
        "SUMMARY",
        sep,
        f"Total tests     : {results['total_tests']}",
        f"Passed          : {results['passed']}",
        f"Failed          : {results['failed']}",
        f"Errors          : {results['errors']}",
        f"Skipped         : {results['skipped']}",
        f"Coverage        : {results['coverage_percent']}%",
        f"Exit code       : {results['exit_code']}",
        f"Succeeded       : {results['execution_succeeded']}",
        f"Failed tests    : {results['failed_test_names']}",
        sep,
        "STDOUT",
        sep,
        results["stdout"],
        sep,
        "STDERR",
        sep,
        results["stderr"],
    ])

    log_path.write_text(content, encoding="utf-8")
    logger.info(f"Execution log saved: {log_path}")


def _clean_test_names(names: list[str]) -> list[str]:
    """Strip ANSI escape codes and deduplicate test names."""
    import re
    ansi = re.compile(r'\x1b\[[0-9;]*m')
    seen, cleaned = set(), []
    for n in names:
        c = ansi.sub('', n).strip()
        if c and c not in seen:
            seen.add(c); cleaned.append(c)
    return cleaned


def executor_node(state: AgentState) -> AgentState:
    """
    Executor node: runs tests in E2B Sandbox or local fallback.

    Reads : state["test_files"], state["source_files"]
    Writes: state["execution_results"], state["failed_tests"],
            state["status"]

    Single Responsibility:
        Execute → Collect → Parse → Update state.
        Nothing else.
    """
    start_time = time.time()

    test_files: list[str] = state.get("test_files", [])
    source_files: list[str] = state.get("source_files", [])
    project_id: str = state.get("project_id", "unknown")
    base_dir: str = state.get("base_dir", "tests/sample_code")

    if not test_files:
        logger.error("No test files in state — Test Writer must run first")
        state["status"] = "failed"
        return state

    logger.info(f"Executor starting — {len(test_files)} test file(s)")

    results: ParsedTestResults
    execution_mode = "e2b_sandbox"

    # E2B is the executor's execution environment. When E2B_API_KEY is
    # configured, sandbox failures are FATAL to the run and surface the real
    # error (no silent local fallback). Local execution remains the fallback
    # only for development setups without an E2B key.
    e2b_configured = bool((os.getenv("E2B_API_KEY") or "").strip())

    if not e2b_configured:
        logger.warning("E2B_API_KEY not configured — local fallback (no sandbox isolation)")
        execution_mode = "local_fallback"
        results = run_tests_locally(test_files, source_files, base_dir)
    else:
        try:
            from e2b_code_interpreter import Sandbox

            manager = SandboxManager()
            logger.info("Spinning up E2B Sandbox")

            sandbox = Sandbox.create(timeout=SandboxManager.SANDBOX_TIMEOUT)
            sandbox_id = getattr(sandbox, "sandbox_id", "unknown")
            try:
                logger.info(f"[E2B] sandbox created: {sandbox_id}")
                manager.upload_files(sandbox, source_files, test_files)
                manager.install_dependencies(sandbox, base_dir)
                logger.info(f"[E2B] running pytest inside sandbox {sandbox_id}")
                stdout, stderr, exit_code = manager.run_pytest_suite(
                    sandbox, test_files, base_dir
                )
                results = parse_pytest_output(stdout, stderr, exit_code)
                logger.info(
                    f"[E2B] pytest finished in sandbox {sandbox_id}: "
                    f"exit={exit_code} total={results['total_tests']} "
                    f"passed={results['passed']} failed={results['failed']}"
                )
            finally:
                sandbox.kill()
                logger.info(f"[E2B] sandbox {sandbox_id} terminated")

        except ImportError as e:
            # Key configured but the SDK is missing — a configuration error,
            # not a reason to switch execution environments.
            error_message = f"E2B execution unavailable (e2b-code-interpreter not installed): {e}"
            logger.error(f"[E2B] {error_message}")
            save_execution_log(project_id, "e2b_sandbox_error", test_files, ParsedTestResults(
                total_tests=0, passed=0, failed=0, errors=1, skipped=0,
                coverage_percent=0.0, failed_test_names=[],
                stdout="", stderr=error_message, exit_code=1, execution_succeeded=False,
            ))
            state["status"] = "failed"
            state["error"] = error_message
            return state

        except Exception as e:
            # E2B configured but execution failed — report the REAL error and
            # stop. Never silently fall back to local pytest.
            error_message = f"E2B execution failed: {type(e).__name__}: {e}"
            logger.exception(f"[E2B] {error_message} — no local fallback (E2B_API_KEY is configured)")
            save_execution_log(project_id, "e2b_sandbox_error", test_files, ParsedTestResults(
                total_tests=0, passed=0, failed=0, errors=1, skipped=0,
                coverage_percent=0.0, failed_test_names=[],
                stdout="", stderr=error_message, exit_code=1, execution_succeeded=False,
            ))
            state["status"] = "failed"
            state["error"] = error_message
            return state

    save_execution_log(project_id, execution_mode, test_files, results)

    elapsed = time.time() - start_time

    ansi = re.compile(r'\x1b\[[0-9;]*m')

    cleaned_failed_names = _clean_test_names(results["failed_test_names"])

    state["execution_results"] = ExecutionResults(
        total_tests=results["total_tests"],
        passed=results["passed"],
        failed=results["failed"],
        errors=results["errors"],
        skipped=results["skipped"],
        coverage_percent=results["coverage_percent"],
        duration_seconds=round(elapsed, 1),
        stdout=ansi.sub('', results["stdout"]),
        stderr=ansi.sub('', results["stderr"]),
        failed_test_names=cleaned_failed_names
    )

    state["failed_tests"] = cleaned_failed_names
    state["status"] = "tests_executed"

    logger.info("=" * 60)
    logger.info("EXECUTOR RESULTS")
    logger.info("=" * 60)
    logger.info(f"Execution mode    : {execution_mode}")
    logger.info(f"Total tests       : {results['total_tests']}")
    logger.info(f"Passed            : {results['passed']} ✅")
    logger.info(f"Failed            : {results['failed']} ❌")
    logger.info(f"Errors            : {results['errors']} ⚠️")
    logger.info(f"Skipped           : {results['skipped']}")
    logger.info(f"Coverage          : {results['coverage_percent']}%")
    
    # Clearer success message
    if results['failed'] == 0 and results['errors'] == 0 and results['total_tests'] > 0:
        logger.info(f"Status            : ALL TESTS PASSED ✅")
    elif results['total_tests'] == 0 and results['errors'] == 0:
        logger.info(f"Status            : NO TESTS COLLECTED / EXECUTED ⚠️")
    else:
        logger.info(f"Status            : {results['passed']}/{results['total_tests']} tests passed ({results['failed']} failed, {results['errors']} errors)")
    
    if results['failed_test_names']:
        logger.info(f"Failed tests      : {results['failed_test_names'][:10]}")
    elif results['failed'] > 0:
        logger.info(f"Failed tests      : {results['failed']} failures (names not extracted)")
    else:
        logger.info(f"Failed tests      : []")
    
    logger.info(f"Execution time    : {elapsed:.1f}s")
    logger.info("=" * 60)

    return state
