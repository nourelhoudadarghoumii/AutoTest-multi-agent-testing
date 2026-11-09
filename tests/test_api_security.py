"""
Security tests: safe archive extraction and pipeline error handling.

The upload path extracts user-supplied archives, so these tests verify
protection against path traversal, absolute paths, and zip bombs.
"""

import json
import zipfile
import tarfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from api.main import _safe_extract_zip, _safe_extract_tar, SecurityError


# ============================================================================
# ZIP extraction security
# ============================================================================

def test_safe_extract_zip_normal_file(tmp_path):
    archive = tmp_path / "proj.zip"
    dest = tmp_path / "out"
    dest.mkdir()

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("module.py", "print('hello')\n")

    with zipfile.ZipFile(archive, "r") as zf:
        _safe_extract_zip(zf, dest)

    assert (dest / "module.py").exists()


def test_safe_extract_zip_path_traversal_attack(tmp_path):
    archive = tmp_path / "evil.zip"
    dest = tmp_path / "out"
    dest.mkdir()

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../../etc/passwd", "malicious")

    with zipfile.ZipFile(archive, "r") as zf:
        with pytest.raises(SecurityError, match="Path traversal"):
            _safe_extract_zip(zf, dest)


def test_safe_extract_zip_absolute_path(tmp_path):
    archive = tmp_path / "evil.zip"
    dest = tmp_path / "out"
    dest.mkdir()

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("/absolute/evil.py", "malicious")

    # Rejected either as an absolute path or (on Windows, where "/" resolves
    # to the drive root) as a path traversal — both are SecurityError.
    with zipfile.ZipFile(archive, "r") as zf:
        with pytest.raises(SecurityError):
            _safe_extract_zip(zf, dest)


def test_safe_extract_zip_file_too_large(tmp_path):
    archive = tmp_path / "big.zip"
    dest = tmp_path / "out"
    dest.mkdir()

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("huge.py", "x" * 1000)

    with zipfile.ZipFile(archive, "r") as zf:
        with pytest.raises(SecurityError, match="too large"):
            _safe_extract_zip(zf, dest, max_file_size=100)


# ============================================================================
# TAR extraction security
# ============================================================================

def test_safe_extract_tar_normal_file(tmp_path):
    archive = tmp_path / "proj.tar.gz"
    dest = tmp_path / "out"
    dest.mkdir()

    with tarfile.open(archive, "w:gz") as tf:
        import io
        info = tarfile.TarInfo(name="module.py")
        data = b"print('hello')"
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

    with tarfile.open(archive, "r:gz") as tf:
        _safe_extract_tar(tf, dest)

    assert (dest / "module.py").exists()


def test_safe_extract_tar_path_traversal(tmp_path):
    archive = tmp_path / "evil.tar.gz"
    dest = tmp_path / "out"
    dest.mkdir()

    with tarfile.open(archive, "w:gz") as tf:
        import io
        info = tarfile.TarInfo(name="../../evil.py")
        data = b"malicious"
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

    with tarfile.open(archive, "r:gz") as tf:
        with pytest.raises(SecurityError, match="Path traversal"):
            _safe_extract_tar(tf, dest)


# ============================================================================
# Pipeline error handling
# ============================================================================

@patch("api.main.build_graph")
@patch("api.main.setup_environment")
def test_execute_pipeline_error_updates_status(mock_setup, mock_build, tmp_path, monkeypatch):
    """A pipeline crash must mark the run as failed with a readable error."""
    import asyncio
    import api.main as api_main

    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "workspace" / "p1" / "runs" / "r1"
    run_dir.mkdir(parents=True)

    mock_build.side_effect = RuntimeError("graph exploded")
    api_main.runs_storage["r1"] = {
        "run_id": "r1", "project_id": "p1", "status": "running",
        "started_at": "2026-01-01T00:00:00",
    }

    asyncio.run(api_main.execute_pipeline("r1", "p1", ["a.py"]))

    assert api_main.runs_storage["r1"]["status"] == "failed"
    assert "graph exploded" in api_main.runs_storage["r1"]["error"]
    assert (run_dir / "error.txt").exists()


# ============================================================================
# SandboxManager — dependency installation contract
# ============================================================================

@patch.dict("os.environ", {"E2B_API_KEY": "test_key"})
def test_sandbox_manager_init_success():
    from agents.executor import SandboxManager
    manager = SandboxManager()
    assert manager.api_key == "test_key"


def test_sandbox_manager_init_missing_api_key(monkeypatch):
    from agents.executor import SandboxManager
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    with pytest.raises(ValueError, match="E2B_API_KEY"):
        SandboxManager()
