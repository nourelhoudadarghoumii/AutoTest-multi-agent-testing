"""
Unit and integration tests for source file management:
- Single file deletion
- Batch file deletion
- Path-traversal attack protection
- Metadata synchronization
- Source file filtering for analysis
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.main import app, WORKSPACE_DIR


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def mock_project():
    """Create a temporary test project in workspace."""
    project_id = "test_file_mgmt_proj"
    proj_dir = WORKSPACE_DIR / project_id
    source_dir = proj_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy python files
    (source_dir / "algo_a.py").write_text("def fn_a(): return 1\n", encoding="utf-8")
    (source_dir / "algo_b.py").write_text("def fn_b(): return 2\n", encoding="utf-8")
    (source_dir / "algo_c.py").write_text("def fn_c(): return 3\n", encoding="utf-8")

    sub_dir = source_dir / "nested"
    sub_dir.mkdir(exist_ok=True)
    (sub_dir / "algo_d.py").write_text("def fn_d(): return 4\n", encoding="utf-8")

    metadata = {
        "project_id": project_id,
        "name": "Test File Management",
        "uploaded_at": "2026-10-30T10:00:00",
        "files_count": 4,
        "files": ["algo_a.py", "algo_b.py", "algo_c.py", "nested/algo_d.py"],
        "source_dir": str(source_dir)
    }
    with open(proj_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    yield project_id, proj_dir, source_dir

    # Cleanup
    import shutil
    shutil.rmtree(proj_dir, ignore_errors=True)


def test_delete_single_file_success(test_client, mock_project):
    project_id, proj_dir, source_dir = mock_project

    # Delete algo_b.py
    resp = test_client.delete(f"/api/projects/{project_id}/source/algo_b.py")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"
    assert data["remaining_files"] == 3

    # Check file is gone on disk
    assert not (source_dir / "algo_b.py").exists()
    assert (source_dir / "algo_a.py").exists()

    # Check metadata was updated
    with open(proj_dir / "metadata.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["files_count"] == 3
    assert "algo_b.py" not in meta["files"]


def test_delete_nested_file_cleans_empty_dir(test_client, mock_project):
    project_id, proj_dir, source_dir = mock_project

    # Delete nested/algo_d.py
    resp = test_client.delete(f"/api/projects/{project_id}/source/nested/algo_d.py")
    assert resp.status_code == 200

    assert not (source_dir / "nested" / "algo_d.py").exists()
    # Parent directory 'nested' should be cleaned if empty
    assert not (source_dir / "nested").exists()


def test_delete_file_path_traversal_blocked(test_client, mock_project):
    project_id, _, _ = mock_project

    # Path traversal in URL path is normalized by client/server or rejected
    resp = test_client.delete(f"/api/projects/{project_id}/source/../../etc/passwd")
    assert resp.status_code in (403, 404, 405)

    # Path traversal in batch deletion
    resp_batch = test_client.post(
        f"/api/projects/{project_id}/source/delete-batch",
        json={"files": ["../../etc/passwd", "../evil.py"]}
    )
    assert resp_batch.status_code == 200
    batch_data = resp_batch.json()
    assert len(batch_data["errors"]) == 2
    assert all("Accès refusé" in err["error"] for err in batch_data["errors"])


def test_delete_file_not_found(test_client, mock_project):
    project_id, _, _ = mock_project

    resp = test_client.delete(f"/api/projects/{project_id}/source/non_existent.py")
    assert resp.status_code == 404


def test_batch_delete_files(test_client, mock_project):
    project_id, proj_dir, source_dir = mock_project

    payload = {
        "files": ["algo_a.py", "algo_c.py"]
    }
    resp = test_client.post(f"/api/projects/{project_id}/source/delete-batch", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["deleted"]) == 2
    assert data["remaining_files"] == 2

    assert not (source_dir / "algo_a.py").exists()
    assert not (source_dir / "algo_c.py").exists()
    assert (source_dir / "algo_b.py").exists()

    with open(proj_dir / "metadata.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["files_count"] == 2
