"""
Coverage metrics: line and branch coverage via coverage.py (JSON report).

Runs the generated test file in a subprocess from the sample's source
directory (same isolation rule as production) with --cov-branch, then reads
percentages from coverage's JSON output. Count parsing reuses production's
parse_pytest_output for the pass/fail summary.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def measure_coverage(
    test_file: Path,
    source_dir: Path,
    entry_file: str,
    timeout_seconds: float = 120.0,
) -> dict:
    """Return line and branch coverage percentages for `entry_file`."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        data_file = Path(tmp) / ".coverage"

        cmd = [
            sys.executable, "-m", "coverage", "run",
            "--branch",
            f"--data-file={data_file}",
            "-m", "pytest", "-q", "--no-header",
            str(Path(test_file).resolve()),
        ]
        run = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(Path(source_dir).resolve()), timeout=timeout_seconds,
        )

        json_path = Path(tmp) / "coverage.json"
        json_cmd = [
            sys.executable, "-m", "coverage", "json",
            f"--data-file={data_file}", "-o", str(json_path), "--quiet",
        ]
        subprocess.run(json_cmd, capture_output=True, text=True, timeout=60)

        if not json_path.exists():
            return {
                "line_coverage": 0.0,
                "branch_coverage": 0.0,
                "executed_lines": 0,
                "missing_lines": 0,
                "covered_branches": 0,
                "total_branches": 0,
                "pytest_exit_code": run.returncode,
                "error": "coverage json not produced",
            }

        data = json.loads(json_path.read_text(encoding="utf-8"))

        target = None
        for file_path, file_data in data.get("files", {}).items():
            if Path(file_path).name == entry_file:
                target = file_data
                break

        if target is None:
            return {
                "line_coverage": 0.0,
                "branch_coverage": 0.0,
                "executed_lines": 0,
                "missing_lines": 0,
                "covered_branches": 0,
                "total_branches": 0,
                "pytest_exit_code": run.returncode,
                "error": f"entry file {entry_file} not found in coverage report",
            }

        summary = target.get("summary", {})
        return {
            "line_coverage": round(summary.get("percent_covered", 0.0), 2),
            "branch_coverage": round(summary.get("covered_branches", 0) / summary.get("num_branches", 1) * 100, 2)
            if summary.get("num_branches") else 0.0,
            "executed_lines": summary.get("covered_lines", 0),
            "missing_lines": summary.get("missing_lines", 0),
            "covered_branches": summary.get("covered_branches", 0),
            "total_branches": summary.get("num_branches", 0),
            "pytest_exit_code": run.returncode,
            "error": None,
        }
