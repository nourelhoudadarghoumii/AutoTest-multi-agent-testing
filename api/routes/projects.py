"""
Projects and Runs API Routes for the frontend.

Provides simplified, real-data access over the workspace directory:
    GET    /api/projects                          - List all projects
    GET    /api/projects/{project_id}             - Project details + runs
    DELETE /api/projects/{project_id}             - Delete a project
    GET    /api/projects/{project_id}/source      - List source files
    GET    /api/projects/{project_id}/source/{path} - Read a source file
    GET    /api/runs                              - List runs (optionally by project)
    GET    /api/stats                             - Aggregated workspace statistics
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

WORKSPACE_DIR = Path("workspace")


class RenameProjectRequest(BaseModel):
    name: str


def _project_name(metadata: dict) -> str:
    """Derive a human-readable project name from upload metadata."""
    if metadata.get("name") and str(metadata["name"]).strip():
        return str(metadata["name"]).strip()
    if metadata.get("filename"):
        return Path(metadata["filename"]).stem
    files = metadata.get("files", [])
    if files:
        return Path(files[0]).stem
    return "Untitled project"


@router.get("/projects")
async def list_projects():
    """List all projects in the workspace, newest first."""
    projects = []

    if not WORKSPACE_DIR.exists():
        return []

    for project_dir in WORKSPACE_DIR.iterdir():
        if not project_dir.is_dir():
            continue

        metadata_file = project_dir / "metadata.json"
        if not metadata_file.exists():
            continue

        try:
            with open(metadata_file, "r") as f:
                metadata = json.load(f)

            runs_dir = project_dir / "runs"
            runs_count = len([d for d in runs_dir.iterdir() if d.is_dir()]) if runs_dir.exists() else 0

            projects.append({
                "id": metadata["project_id"],
                "name": _project_name(metadata),
                "files_count": metadata.get("files_count", 0),
                "uploaded_at": metadata.get("uploaded_at", datetime.now().isoformat()),
                "runs_count": runs_count,
                "status": "active"
            })
        except Exception as e:
            print(f"[WARN] Failed to read project metadata {project_dir}: {e}")
            continue

    projects.sort(key=lambda x: x["uploaded_at"], reverse=True)

    return projects


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get detailed project information including its runs."""
    project_dir = WORKSPACE_DIR / project_id

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    metadata_file = project_dir / "metadata.json"
    if not metadata_file.exists():
        raise HTTPException(status_code=404, detail="Project metadata not found")

    with open(metadata_file, "r") as f:
        metadata = json.load(f)

    runs = []
    runs_dir = project_dir / "runs"
    if runs_dir.exists():
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue

            run_metadata_file = run_dir / "run_metadata.json"
            if run_metadata_file.exists():
                with open(run_metadata_file, "r") as f:
                    run_data = json.load(f)
                    runs.append({
                        "id": run_data["run_id"],
                        "status": run_data.get("status", "unknown"),
                        "started_at": run_data.get("started_at"),
                        "completed_at": run_data.get("completed_at"),
                        "quality_score": run_data.get("quality_score"),
                        "tests_passed": run_data.get("tests_passed"),
                        "tests_total": run_data.get("tests_total"),
                        "coverage": run_data.get("coverage"),
                        "error": run_data.get("error"),
                    })

    runs.sort(key=lambda x: x.get("started_at", ""), reverse=True)

    return {
        "id": metadata["project_id"],
        "name": _project_name(metadata),
        "files_count": metadata.get("files_count", 0),
        "uploaded_at": metadata.get("uploaded_at"),
        "runs": runs,
        "status": "active"
    }


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project and all its runs."""
    project_dir = WORKSPACE_DIR / project_id

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    shutil.rmtree(project_dir)

    return {"message": "Project deleted successfully", "project_id": project_id}


@router.patch("/projects/{project_id}")
@router.put("/projects/{project_id}")
async def rename_project(project_id: str, request: RenameProjectRequest):
    """Rename an existing project and persist in metadata.json."""
    new_name = request.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Project name cannot be empty")

    project_dir = WORKSPACE_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    metadata_file = project_dir / "metadata.json"
    if not metadata_file.exists():
        raise HTTPException(status_code=404, detail="Project metadata not found")

    try:
        with open(metadata_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read project metadata: {e}")

    metadata["name"] = new_name

    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write project metadata: {e}")

    return {
        "project_id": project_id,
        "name": new_name,
        "message": "Project renamed successfully"
    }


@router.get("/projects/{project_id}/source")
async def list_source_files(project_id: str):
    """List all source files in a project."""
    project_dir = WORKSPACE_DIR / project_id
    source_dir = project_dir / "source"

    if not source_dir.exists():
        return []

    files = []
    for file_path in sorted(source_dir.rglob("*.py")):
        files.append({
            "name": file_path.name,
            "path": str(file_path.relative_to(source_dir)),
            "size": file_path.stat().st_size,
        })

    return files


@router.get("/projects/{project_id}/source/{file_path:path}")
async def get_source_file(project_id: str, file_path: str):
    """Get content of a source file (path-traversal protected)."""
    project_dir = WORKSPACE_DIR / project_id
    source_dir = project_dir / "source"
    full_path = (source_dir / file_path).resolve()

    if not str(full_path).startswith(str(source_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = full_path.read_text(encoding="utf-8")
        return {"filename": file_path, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


class BatchDeleteRequest(BaseModel):
    files: list[str]


@router.delete("/projects/{project_id}/source/{file_path:path}")
async def delete_source_file(project_id: str, file_path: str):
    """Delete a single source file from a project (path-traversal protected) and update project metadata."""
    project_dir = WORKSPACE_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Projet introuvable")

    source_dir = project_dir / "source"
    if not source_dir.exists():
        raise HTTPException(status_code=404, detail="Répertoire source introuvable")

    full_path = (source_dir / file_path).resolve()
    if not str(full_path).startswith(str(source_dir.resolve())):
        raise HTTPException(status_code=403, detail="Accès refusé (tentative d'évasion de chemin)")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    try:
        full_path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression du fichier: {str(e)}")

    # Clean empty parent directories up to source_dir
    parent = full_path.parent
    source_resolved = source_dir.resolve()
    while parent != source_resolved and parent.exists():
        try:
            parent.rmdir()
            parent = parent.parent
        except OSError:
            break

    # Recalculate remaining Python files
    remaining_files = list(source_dir.rglob("*.py"))
    remaining_count = len(remaining_files)

    metadata_file = project_dir / "metadata.json"
    if metadata_file.exists():
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            metadata["files_count"] = remaining_count
            if "files" in metadata and isinstance(metadata["files"], list):
                norm_del = Path(file_path).as_posix()
                del_name = Path(file_path).name
                metadata["files"] = [
                    f for f in metadata["files"]
                    if Path(f).as_posix() != norm_del and Path(f).name != del_name
                ]
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            print(f"[WARN] Failed to update metadata.json after deleting {file_path}: {e}")

    return {
        "status": "deleted",
        "file": file_path,
        "remaining_files": remaining_count,
        "message": f"Fichier {file_path} supprimé avec succès."
    }


@router.post("/projects/{project_id}/source/delete-batch")
async def delete_source_files_batch(project_id: str, request: BatchDeleteRequest):
    """Delete multiple source files in batch (path-traversal protected) and update project metadata."""
    project_dir = WORKSPACE_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Projet introuvable")

    source_dir = project_dir / "source"
    if not source_dir.exists():
        raise HTTPException(status_code=404, detail="Répertoire source introuvable")

    deleted = []
    errors = []
    source_resolved = source_dir.resolve()

    for file_path in request.files:
        full_path = (source_dir / file_path).resolve()
        if not str(full_path).startswith(str(source_resolved)):
            errors.append({"file": file_path, "error": "Accès refusé"})
            continue

        if not full_path.exists() or not full_path.is_file():
            errors.append({"file": file_path, "error": "Fichier introuvable"})
            continue

        try:
            full_path.unlink()
            deleted.append(file_path)

            parent = full_path.parent
            while parent != source_resolved and parent.exists():
                try:
                    parent.rmdir()
                    parent = parent.parent
                except OSError:
                    break
        except Exception as e:
            errors.append({"file": file_path, "error": str(e)})

    # Recalculate remaining Python files
    remaining_files = list(source_dir.rglob("*.py"))
    remaining_count = len(remaining_files)

    metadata_file = project_dir / "metadata.json"
    if metadata_file.exists():
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            metadata["files_count"] = remaining_count
            if "files" in metadata and isinstance(metadata["files"], list):
                deleted_posix = {Path(p).as_posix() for p in deleted}
                deleted_names = {Path(p).name for p in deleted}
                metadata["files"] = [
                    f for f in metadata["files"]
                    if Path(f).as_posix() not in deleted_posix and Path(f).name not in deleted_names
                ]
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            print(f"[WARN] Failed to update metadata.json after batch delete: {e}")

    return {
        "status": "completed",
        "deleted": deleted,
        "errors": errors,
        "remaining_files": remaining_count,
        "message": f"{len(deleted)} fichier(s) supprimé(s)."
    }


@router.get("/runs")
async def list_runs(project_id: Optional[str] = None):
    """List all test runs, optionally filtered by project."""
    runs = []

    if not WORKSPACE_DIR.exists():
        return []

    if project_id:
        project_dir = WORKSPACE_DIR / project_id
        if not project_dir.exists():
            raise HTTPException(status_code=404, detail="Project not found")
        project_dirs = [project_dir]
    else:
        project_dirs = [d for d in WORKSPACE_DIR.iterdir() if d.is_dir()]

    for project_dir in project_dirs:
        runs_dir = project_dir / "runs"
        if not runs_dir.exists():
            continue

        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue

            run_metadata_file = run_dir / "run_metadata.json"
            if not run_metadata_file.exists():
                continue

            try:
                with open(run_metadata_file, "r") as f:
                    run_data = json.load(f)

                runs.append({
                    "id": run_data["run_id"],
                    "project_id": run_data["project_id"],
                    "status": run_data.get("status", "unknown"),
                    "started_at": run_data.get("started_at"),
                    "completed_at": run_data.get("completed_at"),
                    "quality_score": run_data.get("quality_score"),
                    "tests_passed": run_data.get("tests_passed"),
                    "tests_total": run_data.get("tests_total"),
                    "coverage": run_data.get("coverage"),
                    "error": run_data.get("error"),
                })
            except Exception as e:
                print(f"[WARN] Failed to read run metadata {run_dir}: {e}")
                continue

    runs.sort(key=lambda x: x.get("started_at", ""), reverse=True)

    return runs


@router.get("/stats")
async def get_workspace_stats():
    """
    Aggregated workspace statistics computed from real run metadata.
    Contains no synthetic data — every number derives from stored runs.
    """
    total_projects = 0
    completed_runs = 0
    failed_runs = 0
    total_tests = 0
    quality_scores: list[float] = []
    coverage_scores: list[float] = []

    if WORKSPACE_DIR.exists():
        for project_dir in WORKSPACE_DIR.iterdir():
            if not project_dir.is_dir() or not (project_dir / "metadata.json").exists():
                continue
            total_projects += 1

            runs_dir = project_dir / "runs"
            if not runs_dir.exists():
                continue

            for run_dir in runs_dir.iterdir():
                metadata_file = run_dir / "run_metadata.json"
                if not metadata_file.exists():
                    continue
                try:
                    with open(metadata_file, "r") as f:
                        run_data = json.load(f)
                except Exception:
                    continue

                status = run_data.get("status")
                if status == "completed":
                    completed_runs += 1
                    if run_data.get("quality_score") is not None:
                        quality_scores.append(float(run_data["quality_score"]))
                    if run_data.get("coverage") is not None:
                        coverage_scores.append(float(run_data["coverage"]))
                    total_tests += int(run_data.get("tests_total") or 0)
                elif status == "failed":
                    failed_runs += 1

    return {
        "total_projects": total_projects,
        "completed_runs": completed_runs,
        "failed_runs": failed_runs,
        "total_tests_generated": total_tests,
        "average_quality": round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else None,
        "average_coverage": round(sum(coverage_scores) / len(coverage_scores), 1) if coverage_scores else None,
    }
