"""
FastAPI REST API for AutoTest — the AI-powered Python testing workspace.

Main endpoints:
    POST   /v1/projects/upload              - Upload a Python project (files or archive)
    POST   /v1/projects/{id}/analyze        - Trigger the multi-agent pipeline
    GET    /v1/runs/{run_id}                - Check run status
    GET    /v1/runs/{run_id}/stream         - Live progress (SSE)
    GET    /v1/runs/{run_id}/report         - Quality report (JSON / markdown)
    GET    /v1/runs/{run_id}/tests[/{file}] - Generated test code
    GET    /v1/runs/{run_id}/tests/download - Download generated tests (ZIP)
    GET    /v1/runs/{run_id}/package        - Download full results package (ZIP)

There is a single user experience: the engineer workspace.
No authentication is required — the tool is designed for direct local use.
"""

import json
import os
import shutil
import tarfile
import tempfile
import zipfile
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal, AsyncGenerator
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.graph import build_graph, setup_environment
from core.state import AgentState

logger = logging.getLogger(__name__)

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


# =============================================================================
# Configuration
# =============================================================================

API_VERSION = "1.0.0"

WORKSPACE_DIR = Path("workspace")
WORKSPACE_DIR.mkdir(exist_ok=True)

# Upload configuration
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "100"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024


# =============================================================================
# Secure Archive Extraction
# =============================================================================

class SecurityError(Exception):
    """Raised when archive security validation fails."""


def _safe_extract_zip(zip_file: zipfile.ZipFile, dest_path: Path, max_file_size: int = 50 * 1024 * 1024) -> None:
    """
    Safely extract ZIP file with security validation.

    Protects against:
    - Path traversal attacks (../../etc/passwd)
    - Zip bombs (small compressed → huge decompressed)
    - Malicious filenames
    """
    dest_path = dest_path.resolve()

    for member in zip_file.namelist():
        # 1. Prevent path traversal
        member_path = (dest_path / member).resolve()
        if not str(member_path).startswith(str(dest_path)):
            raise SecurityError(f"Path traversal detected: {member}")

        # 2. Prevent absolute paths
        if member.startswith('/') or member.startswith('\\'):
            raise SecurityError(f"Absolute path not allowed: {member}")

        # 3. Check file size (prevent zip bombs)
        info = zip_file.getinfo(member)
        if info.file_size > max_file_size:
            raise SecurityError(
                f"File too large: {member} ({info.file_size / (1024*1024):.1f}MB > {max_file_size / (1024*1024):.0f}MB)"
            )

    zip_file.extractall(dest_path)


def _safe_extract_tar(tar_file, dest_path: Path, max_file_size: int = 50 * 1024 * 1024) -> None:
    """Safely extract TAR.GZ file with security validation."""
    dest_path = dest_path.resolve()

    for member in tar_file.getmembers():
        member_path = (dest_path / member.name).resolve()
        if not str(member_path).startswith(str(dest_path)):
            raise SecurityError(f"Path traversal detected: {member.name}")

        if member.name.startswith('/') or member.name.startswith('\\'):
            raise SecurityError(f"Absolute path not allowed: {member.name}")

        if member.size > max_file_size:
            raise SecurityError(
                f"File too large: {member.name} ({member.size / (1024*1024):.1f}MB > {max_file_size / (1024*1024):.0f}MB)"
            )

    tar_file.extractall(dest_path)


# =============================================================================
# Pydantic Models
# =============================================================================

class ProjectUploadResponse(BaseModel):
    """Response for project upload."""
    project_id: str
    message: str
    files_count: int
    upload_timestamp: str


class AnalyzeRequest(BaseModel):
    """Request body for analyze endpoint."""
    source_files: Optional[list[str]] = Field(
        None,
        description="Specific files to analyze (relative paths). If omitted, analyzes all Python files."
    )


class AnalyzeResponse(BaseModel):
    """Response for analyze trigger."""
    run_id: str
    project_id: str
    status: Literal["queued", "running"]
    message: str
    started_at: str


class RunStatus(BaseModel):
    """Run status response."""
    run_id: str
    project_id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: str
    started_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None


class ReportResponse(BaseModel):
    """Quality report response."""
    run_id: str
    project_id: str
    report: dict
    generated_at: str


# =============================================================================
# In-Memory Run Storage (production: Redis/PostgreSQL)
# =============================================================================

runs_storage: dict[str, dict] = {}


def _find_run_dir(run_id: str) -> Optional[Path]:
    """Locate a run directory under workspace/<project>/runs/<run_id>."""
    if run_id in runs_storage:
        project_id = runs_storage[run_id].get("project_id")
        if project_id:
            candidate = WORKSPACE_DIR / project_id / "runs" / run_id
            if candidate.exists():
                return candidate
    for project_dir in WORKSPACE_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        candidate = project_dir / "runs" / run_id
        if candidate.exists():
            return candidate
    return None


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="AutoTest API",
    description="AI-powered autonomous Python testing: Analyser → Test Writer → Executor ↔ Debugger → Reporter",
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers (projects listing, runs, source files)
from api.routes.projects import router as projects_router  # noqa: E402
app.include_router(projects_router, prefix="/api")

# Mount React frontend build (production)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    logger.info("React frontend mounted from %s", frontend_dist)


# =============================================================================
# Health & Root
# =============================================================================

@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint with real configuration status."""
    from llm import configured_models
    llm_configured = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    return {
        "status": "ok",
        "version": API_VERSION,
        "llm_models": configured_models(),
        "llm_configured": llm_configured,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/")
async def root():
    """Serve the React web interface."""
    if frontend_dist.exists():
        return FileResponse(frontend_dist / "index.html")
    raise HTTPException(
        status_code=503,
        detail="Frontend not built. Run: cd frontend && npm run build"
    )


# =============================================================================
# Upload Endpoints
# =============================================================================

@app.post("/v1/projects/upload", response_model=ProjectUploadResponse)
async def upload_project(
    file: Optional[UploadFile] = File(None),
    files: Optional[list[UploadFile]] = File(None),
) -> ProjectUploadResponse:
    """
    Upload a project for testing.

    Accepts:
        - Single archive: ZIP or TAR.GZ file containing Python source code
        - Multiple files: one or more .py files
    """
    if not file and not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if files:
        return await handle_python_files_upload(files)

    if file:
        return await handle_archive_upload(file)

    raise HTTPException(status_code=400, detail="Invalid upload request")


async def handle_python_files_upload(files: list[UploadFile]) -> ProjectUploadResponse:
    """Handle upload of multiple .py files."""
    for f in files:
        if not f.filename or not f.filename.endswith('.py'):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {f.filename}. Only .py files are allowed."
            )

    project_id = str(uuid4())
    project_dir = WORKSPACE_DIR / project_id
    source_dir = project_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for f in files:
        content = await f.read()

        if len(content) > 10 * 1024 * 1024:
            shutil.rmtree(project_dir, ignore_errors=True)
            raise HTTPException(
                status_code=413,
                detail=f"File {f.filename} exceeds 10MB limit"
            )

        if len(content) == 0:
            continue  # Skip empty files

        # Prevent path traversal via crafted filenames
        file_path = (source_dir / Path(f.filename).name)
        with open(file_path, "wb") as target:
            target.write(content)
        saved_files.append(file_path.name)

    if not saved_files:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="No valid Python files found")

    metadata = {
        "project_id": project_id,
        "uploaded_at": datetime.now().isoformat(),
        "upload_type": "python_files",
        "files_count": len(saved_files),
        "files": saved_files,
        "source_dir": str(source_dir)
    }

    with open(project_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return ProjectUploadResponse(
        project_id=project_id,
        message=f"Uploaded {len(saved_files)} Python files successfully",
        files_count=len(saved_files),
        upload_timestamp=metadata["uploaded_at"]
    )


async def handle_archive_upload(file: UploadFile) -> ProjectUploadResponse:
    """Handle upload of ZIP or TAR.GZ archive."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not (file.filename.endswith('.zip') or file.filename.endswith('.tar.gz') or file.filename.endswith('.tgz')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only .zip, .tar.gz, and .tgz are supported."
        )

    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)

    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {MAX_UPLOAD_SIZE_MB}MB. Your file: {file_size_mb:.1f}MB"
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    project_id = str(uuid4())
    project_dir = WORKSPACE_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    upload_path = project_dir / Path(file.filename).name
    with open(upload_path, "wb") as f:
        f.write(content)

    try:
        if file.filename.endswith('.zip'):
            with zipfile.ZipFile(upload_path, 'r') as zip_ref:
                _safe_extract_zip(zip_ref, project_dir / "source")
        else:  # tar.gz or tgz
            with tarfile.open(upload_path, 'r:gz') as tar_ref:
                _safe_extract_tar(tar_ref, project_dir / "source")
    except SecurityError as e:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Security validation failed: {str(e)}")
    except Exception as e:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Failed to extract archive: {str(e)}")
    finally:
        upload_path.unlink(missing_ok=True)

    source_dir = project_dir / "source"
    py_files = list(source_dir.rglob("*.py"))

    if not py_files:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail="No Python files found in the uploaded archive."
        )

    metadata = {
        "project_id": project_id,
        "uploaded_at": datetime.now().isoformat(),
        "upload_type": "archive",
        "filename": file.filename,
        "files_count": len(py_files),
        "source_dir": str(source_dir)
    }

    with open(project_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return ProjectUploadResponse(
        project_id=project_id,
        message="Project uploaded successfully",
        files_count=len(py_files),
        upload_timestamp=metadata["uploaded_at"]
    )


# =============================================================================
# Pipeline Execution
# =============================================================================

@app.post("/v1/projects/{project_id}/analyze", response_model=AnalyzeResponse)
async def analyze_project(
    project_id: str,
    background_tasks: BackgroundTasks,
    request: Optional[AnalyzeRequest] = None,
) -> AnalyzeResponse:
    """
    Trigger the multi-agent pipeline for a project:
    Analyser → Test Writer → Executor ↔ Debugger → Reporter
    """
    project_dir = WORKSPACE_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found. Upload it first.")

    metadata_path = project_dir / "metadata.json"
    if not metadata_path.exists():
        raise HTTPException(status_code=500, detail="Project metadata missing.")

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    source_dir = Path(metadata["source_dir"])

    if request and request.source_files:
        source_files = []
        source_dir_resolved = source_dir.resolve()
        for f in request.source_files:
            file_path = (source_dir / f).resolve()
            if not str(file_path).startswith(str(source_dir_resolved)):
                raise HTTPException(status_code=403, detail=f"Access denied: {f}")
            if not file_path.exists() or not file_path.is_file():
                raise HTTPException(status_code=400, detail=f"Source file not found: {f}")
            source_files.append(str(file_path))
    else:
        source_files = [str(f) for f in source_dir.rglob("*.py")]

    if not source_files:
        raise HTTPException(status_code=400, detail="No source files to analyze.")

    run_id = str(uuid4())
    run_dir = project_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    run_metadata = {
        "run_id": run_id,
        "project_id": project_id,
        "status": "queued",
        "started_at": datetime.now().isoformat(),
        "source_files": source_files,
    }

    runs_storage[run_id] = run_metadata

    with open(run_dir / "run_metadata.json", "w", encoding="utf-8") as f:
        json.dump(run_metadata, f, indent=2)

    background_tasks.add_task(execute_pipeline, run_id, project_id, source_files)

    return AnalyzeResponse(
        run_id=run_id,
        project_id=project_id,
        status="queued",
        message="Analysis queued successfully. Use /v1/runs/{run_id} to check status.",
        started_at=run_metadata["started_at"]
    )


@app.get("/v1/runs/{run_id}", response_model=RunStatus)
async def get_run_status(run_id: str) -> RunStatus:
    """Get analysis run status."""
    run_data = _load_run_data(run_id)

    return RunStatus(
        run_id=run_id,
        project_id=run_data["project_id"],
        status=run_data["status"],
        progress=run_data.get("progress", "Initializing..."),
        started_at=run_data["started_at"],
        completed_at=run_data.get("completed_at"),
        error=run_data.get("error")
    )


def _load_run_data(run_id: str) -> dict:
    """Load run metadata from memory or disk."""
    if run_id in runs_storage:
        return runs_storage[run_id]

    run_dir = _find_run_dir(run_id)
    metadata_file = run_dir / "run_metadata.json" if run_dir else None
    if not metadata_file or not metadata_file.exists():
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

    with open(metadata_file, "r", encoding="utf-8") as f:
        run_data = json.load(f)
    runs_storage[run_id] = run_data
    return run_data


@app.get("/v1/runs/{run_id}/stream")
async def stream_run_progress(run_id: str):
    """
    Stream real-time progress updates using Server-Sent Events (SSE).
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        last_status = None
        last_progress = None

        for _ in range(1800):  # 30 minutes max (1800 * 1s) — LLM runs can be long
            await asyncio.sleep(1)

            try:
                run_data = _load_run_data(run_id)
            except HTTPException:
                yield f"data: {json.dumps({'error': 'Run not found'})}\n\n"
                return

            status = run_data.get("status")
            progress = run_data.get("progress", "Processing...")
            current_agent = run_data.get("current_agent", "")

            if status != last_status or progress != last_progress:
                event_data = {
                    "status": status,
                    "progress": progress,
                    "current_agent": current_agent,
                    "timestamp": datetime.now().isoformat()
                }

                if status in ["completed", "failed"]:
                    event_data["quality_score"] = run_data.get("quality_score")
                    event_data["coverage"] = run_data.get("coverage")
                    event_data["tests_passed"] = run_data.get("tests_passed")
                    event_data["tests_total"] = run_data.get("tests_total")
                    event_data["error"] = run_data.get("error")

                yield f"data: {json.dumps(event_data)}\n\n"

                last_status = status
                last_progress = progress

                if status in ["completed", "failed"]:
                    return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/v1/runs/{run_id}/report", response_model=ReportResponse)
async def get_run_report(
    run_id: str,
    format: Literal["json", "markdown"] = "json"
):
    """Get the quality report for a completed run."""
    run_data = _load_run_data(run_id)

    if run_data["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Run is not completed yet. Current status: {run_data['status']}"
        )

    run_dir = _find_run_dir(run_id)
    if not run_dir:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

    if format == "markdown":
        md_path = run_dir / "final_report.md"
        if md_path.exists():
            return FileResponse(
                md_path,
                media_type="text/markdown",
                filename=f"report_{run_id[:8]}.md"
            )
        raise HTTPException(status_code=500, detail="Markdown report not available.")

    report_path = run_dir / "final_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=500, detail="Report file missing.")

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    return ReportResponse(
        run_id=run_id,
        project_id=run_data["project_id"],
        report=report,
        generated_at=run_data.get("completed_at", datetime.now().isoformat())
    )


# =============================================================================
# Generated Test Files
# =============================================================================

@app.get("/v1/runs/{run_id}/tests")
async def list_test_files(run_id: str):
    """List all generated test files for a run."""
    run_dir = _find_run_dir(run_id)
    if not run_dir:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    tests_dir = run_dir / "tests"
    if not tests_dir.exists():
        return []

    files = []
    for test_file in sorted(tests_dir.glob("*.py")):
        files.append({
            "filename": test_file.name,
            "path": str(test_file.relative_to(tests_dir)),
            "size": test_file.stat().st_size,
        })

    return files


@app.get("/v1/runs/{run_id}/tests/download")
async def download_tests(run_id: str):
    """Download generated test files as a ZIP archive.

    NOTE: must be declared before /tests/{filename} so "download" is not
    captured as a filename path parameter.
    """
    run_dir = _find_run_dir(run_id)
    if not run_dir:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

    tests_dir = run_dir / "tests"

    if not tests_dir.exists() or not any(tests_dir.glob("test_*.py")):
        raise HTTPException(status_code=404, detail="No test files generated.")

    zip_path = run_dir / f"tests_{run_id}.zip"

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for test_file in tests_dir.glob("test_*.py"):
            zipf.write(test_file, arcname=test_file.name)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"autotest_tests_{run_id[:8]}.zip"
    )


@app.get("/v1/runs/{run_id}/tests/{filename}")
async def get_test_file(run_id: str, filename: str):
    """Get content of a generated test file."""
    run_dir = _find_run_dir(run_id)
    if not run_dir:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    test_file = run_dir / "tests" / Path(filename).name

    if not test_file.name.endswith('.py'):
        raise HTTPException(status_code=403, detail="Only .py files allowed")

    if not test_file.exists():
        raise HTTPException(status_code=404, detail="Test file not found")

    try:
        content = test_file.read_text(encoding="utf-8")
        return {"filename": filename, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


@app.get("/v1/runs/{run_id}/package")
async def download_full_package(run_id: str):
    """
    Download the complete results package: generated tests, reports, logs.
    """
    run_dir = _find_run_dir(run_id)
    if not run_dir:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

    zip_path = run_dir / f"autotest_package_{run_id}.zip"

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        tests_dir = run_dir / "tests"
        if tests_dir.exists():
            for test_file in tests_dir.rglob("*.py"):
                zipf.write(test_file, arcname=f"tests/{test_file.relative_to(tests_dir)}")

        for report_file in ["final_report.json", "final_report.md"]:
            report_path = run_dir / report_file
            if report_path.exists():
                zipf.write(report_path, arcname=f"reports/{report_file}")

        metadata_path = run_dir / "run_metadata.json"
        if metadata_path.exists():
            zipf.write(metadata_path, arcname="metadata.json")

        error_path = run_dir / "error.txt"
        if error_path.exists():
            zipf.write(error_path, arcname="logs/error.txt")

        readme_content = f"""# AutoTest Analysis Results
Run ID: {run_id}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Contents
- `tests/` - Generated pytest test files
- `reports/` - Quality reports (JSON and Markdown)
- `metadata.json` - Run configuration and metadata
- `logs/` - Execution logs (if available)

## Usage
1. Extract this archive to your project directory
2. Install pytest: `pip install pytest pytest-cov`
3. Run tests: `pytest tests/`
4. View coverage: `pytest --cov tests/`

## Report
See `reports/final_report.md` for detailed analysis and recommendations.

---
Generated by AutoTest
"""
        zipf.writestr("README.md", readme_content)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"autotest_complete_{run_id[:8]}.zip"
    )


# =============================================================================
# Background Pipeline Execution
# =============================================================================

async def execute_pipeline(run_id: str, project_id: str, source_files: list[str]):
    """Execute the multi-agent pipeline in the background."""
    run_dir = WORKSPACE_DIR / project_id / "runs" / run_id

    try:
        runs_storage[run_id]["status"] = "running"
        runs_storage[run_id]["progress"] = "Initialisation du pipeline..."
        runs_storage[run_id]["current_agent"] = "initializing"

        setup_environment()
        app_graph = build_graph()

        # Absolute paths: background tasks may resolve relative paths against
        # a different cwd once subprocesses change directory.
        project_source = str((WORKSPACE_DIR / project_id / "source").resolve())
        absolute_test_dir = str((run_dir / "tests").resolve())

        initial_state: AgentState = {
            "project_id": project_id,
            "base_dir": project_source,
            "test_dir": absolute_test_dir,
            "source_files": source_files,
            "code_context": {
                "functions": [],
                "classes": [],
                "imports": [],
                "complexity": {},
                "dependency_graph": {}
            },
            "analysis": {
                "files": [],
                "total_files": 0,
                "total_functions": 0,
                "total_classes": 0,
                "total_risk_zones": 0,
                "avg_complexity": 0.0,
                "top_risk_functions": [],
                "external_imports": []
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
            "execution_results": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "coverage_percent": 0.0,
                "duration_seconds": 0.0,
                "stdout": "",
                "stderr": "",
                "failed_test_names": []
            },
            "failed_tests": [],
            "debug_report": {
                "root_cause": "",
                "fix_applied": "",
                "iterations": 0,
                "resolved": False
            },
            "debug_history": [],
            "iteration_count": 0,
            "total_fixes_applied": 0,
            "final_report": {},
            "error": "",
            "status": "running"
        }

        runs_storage[run_id]["progress"] = "Analyse statique du code source..."
        runs_storage[run_id]["current_agent"] = "analyser"

        logger.info("[Pipeline] Starting execution for run %s", run_id)

        final_state = await asyncio.to_thread(app_graph.invoke, initial_state)

        logger.info("[Pipeline] Execution completed for run %s (status: %s)",
                    run_id, final_state.get("status", "unknown"))

        # A failed pipeline (e.g. LLM unavailable) ends as failed — never as a
        # zero-test "completed" run.
        if final_state.get("status") == "failed":
            error_message = final_state.get("error") or "Pipeline failed during test generation."
            runs_storage[run_id]["status"] = "failed"
            runs_storage[run_id]["error"] = error_message
            runs_storage[run_id]["completed_at"] = datetime.now().isoformat()
            runs_storage[run_id]["progress"] = f"Échec du pipeline : {error_message}"
            runs_storage[run_id]["current_agent"] = "error"

            error_path = run_dir / "error.txt"
            error_path.parent.mkdir(parents=True, exist_ok=True)
            with open(error_path, "w", encoding="utf-8") as f:
                f.write("Pipeline Execution Error\n")
                f.write("=" * 60 + "\n")
                f.write(f"Run ID: {run_id}\n")
                f.write(f"Project ID: {project_id}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Error: {error_message}\n")
            logger.error("[Pipeline] Run %s failed: %s", run_id, error_message)
            return

        # Save report
        from agents.reporter import export_report_json, export_report_markdown

        report = final_state.get("final_report", {})
        export_report_json(report, run_dir / "final_report.json")
        export_report_markdown(report, run_dir / "final_report.md")

        runs_storage[run_id]["status"] = "completed"
        runs_storage[run_id]["completed_at"] = datetime.now().isoformat()
        runs_storage[run_id]["progress"] = "Pipeline terminé avec succès"
        runs_storage[run_id]["current_agent"] = "completed"
        runs_storage[run_id]["quality_score"] = report.get("quality_score", 0.0)
        runs_storage[run_id]["coverage"] = report.get("coverage_percent", 0.0)
        runs_storage[run_id]["tests_passed"] = report.get("passed", 0)
        runs_storage[run_id]["tests_total"] = report.get("total_tests", 0)

        logger.info("[Pipeline] Quality Score: %s/100", report.get("quality_score"))
        logger.info("[Pipeline] Coverage: %s%%", report.get("coverage_percent"))
        logger.info("[Pipeline] Tests: %s/%s passed",
                    report.get("passed"), report.get("total_tests"))

    except Exception as e:
        error_trace = __import__("traceback").format_exc()
        error_message = str(e)

        logger.exception("[Pipeline] FATAL ERROR in run %s", run_id)

        runs_storage[run_id]["status"] = "failed"
        runs_storage[run_id]["error"] = error_message
        runs_storage[run_id]["error_type"] = type(e).__name__
        runs_storage[run_id]["completed_at"] = datetime.now().isoformat()
        runs_storage[run_id]["progress"] = f"Échec du pipeline : {error_message}"
        runs_storage[run_id]["current_agent"] = "error"

        # Save error trace for the results package
        error_path = run_dir / "error.txt"
        error_path.parent.mkdir(parents=True, exist_ok=True)
        with open(error_path, "w", encoding="utf-8") as f:
            f.write("Pipeline Execution Error\n")
            f.write("=" * 60 + "\n")
            f.write(f"Run ID: {run_id}\n")
            f.write(f"Project ID: {project_id}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Error Type: {type(e).__name__}\n")
            f.write(f"Error Message: {error_message}\n")
            f.write("\n" + "=" * 60 + "\n")
            f.write("Full Traceback:\n")
            f.write("=" * 60 + "\n")
            f.write(error_trace)

    finally:
        with open(run_dir / "run_metadata.json", "w", encoding="utf-8") as f:
            json.dump(runs_storage[run_id], f, indent=2)


# =============================================================================
# Startup Event
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Print startup status. The server starts even without an LLM key —
    the pipeline fails gracefully with an actionable error in that case."""
    # Make the LLM service's per-agent lines visible in server logs
    # ("LLM service initialized — agent: X, model: Y") for auditability.
    llm_logger = logging.getLogger("llm")
    if not llm_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
        llm_logger.addHandler(handler)
        llm_logger.setLevel(logging.INFO)
        llm_logger.propagate = False

    print()
    print("=" * 60)
    print("        AutoTest - Python Test Engineering & Quality Audit")
    print("=" * 60)
    print()

    from config import LLMConfig

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    if openrouter_key:
        print("[OK] LLM configured (fixed models, no fallbacks):")
        print(f"    Test Writer : {LLMConfig.TEST_WRITER_MODEL}")
        print(f"    Debugger    : {LLMConfig.DEBUGGER_MODEL}")
    else:
        print("[!] OPENROUTER_API_KEY not configured")
        print("  Test generation will fail until you add it to .env")
        print("  Get a key at https://openrouter.ai/keys")

    e2b_key = os.getenv("E2B_API_KEY")
    if e2b_key and e2b_key != "YOUR_KEY_HERE":
        print("[OK] E2B Sandbox enabled (isolated test execution)")
    else:
        print("[-] E2B not configured - using local test execution")

    print()
    print("API Server:")
    print("  Web UI:     http://localhost:8000/")
    print("  API Docs:   http://localhost:8000/docs")
    print()
    print("Ready.")
    print("=" * 60)
    print()


# =============================================================================
# SPA Catch-all Route (for React Router)
# =============================================================================

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """
    Catch-all route to serve the React SPA for client-side routing.
    API routes (/v1/*, /api/*, /health, /docs) are matched first.
    """
    if full_path.startswith(("v1/", "api/", "health", "docs", "redoc", "openapi.json", "assets/")):
        raise HTTPException(status_code=404, detail="API endpoint not found")

    if frontend_dist.exists():
        return FileResponse(frontend_dist / "index.html")
    raise HTTPException(
        status_code=503,
        detail="Frontend not built. Run: cd frontend && npm run build"
    )
