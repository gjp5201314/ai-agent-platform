"""
Sandbox management API — health, code execution, dependencies, files.

All endpoints use POST with JSON body (read operations included).
"""
from fastapi import APIRouter, HTTPException, UploadFile, File

from app.core.sandbox import (
    ExecutionResult,
    SandboxHealth,
    SandboxLanguage,
    get_sandbox_client,
    validate_sandbox_code,
)
from app.core.logger import logger

router = APIRouter()


# ---------------------------------------------------------------------------
#  Health
# ---------------------------------------------------------------------------

@router.post("/health")
async def sandbox_health() -> dict:
    """Check if the DifySandbox service is reachable and healthy."""
    client = get_sandbox_client()
    health: SandboxHealth = await client.health()

    return {
        "status": "ok" if health.reachable else "unreachable",
        "reachable": health.reachable,
        "latency_ms": health.latency_ms,
        "error": health.error if not health.reachable else None,
    }


# ---------------------------------------------------------------------------
#  Code execution
# ---------------------------------------------------------------------------

@router.post("/run")
async def sandbox_run(body: dict) -> dict:
    """
    Execute code in the sandbox.

    Request body:
      - code: str (required) — source code to execute
      - language: str (optional, default "python3") — python3 | javascript | bash
      - enable_network: bool (optional, default false)

    Returns:
      - success, stdout, stderr, error, exit_code, elapsed_ms
    """
    code = body.get("code", "")
    language_str = body.get("language", "python3")
    enable_network = body.get("enable_network", False)

    # Validate language
    try:
        language = SandboxLanguage(language_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: '{language_str}'. Supported: python3, javascript, bash",
        )

    # Pre-flight validation
    is_safe, err_msg = validate_sandbox_code(code, enable_network=enable_network)
    if not is_safe:
        raise HTTPException(status_code=400, detail=err_msg)

    client = get_sandbox_client()
    result: ExecutionResult = await client.run_code(
        code=code,
        language=language,
        enable_network=enable_network,
    )

    return {
        "success": result.success,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "error": result.error,
        "exit_code": result.exit_code,
        "elapsed_ms": result.elapsed_ms,
    }


# ---------------------------------------------------------------------------
#  Dependencies
# ---------------------------------------------------------------------------

@router.post("/dependencies/list")
async def list_dependencies() -> dict:
    """List installed Python packages in the sandbox."""
    client = get_sandbox_client()
    deps = await client.list_dependencies()
    return {
        "packages": deps.packages,
        "count": deps.count,
    }


@router.post("/dependencies/install")
async def install_dependencies(body: dict) -> dict:
    """
    Install Python packages in the sandbox.

    Request body:
      - packages: list[str] (required) — package names, e.g. ["numpy", "pandas==2.0"]
    """
    packages = body.get("packages", [])
    if not packages or not isinstance(packages, list):
        raise HTTPException(status_code=400, detail="'packages' must be a non-empty list of package names.")

    # Sanitize: only allow alphanumeric, -, _, ., ==, >=, <=, >, <
    import re
    for pkg in packages:
        if not re.match(r'^[a-zA-Z0-9\-_\.\[\]<>=!~;,\s]+$', pkg):
            raise HTTPException(status_code=400, detail=f"Invalid package name: '{pkg}'")

    client = get_sandbox_client()
    result_msg = await client.install_dependencies(packages)

    return {
        "message": result_msg,
        "requested": packages,
    }


@router.post("/dependencies/ensure-datascience")
async def ensure_data_science() -> dict:
    """Install common data science packages (numpy, pandas, matplotlib) if missing."""
    client = get_sandbox_client()
    result = await client.ensure_data_science_packages()
    return {"message": result}


# ---------------------------------------------------------------------------
#  Files
# ---------------------------------------------------------------------------

@router.post("/files/list")
async def list_files() -> dict:
    """List files in the sandbox working directory."""
    client = get_sandbox_client()
    files = await client.list_files()
    return {"files": files, "count": len(files)}


@router.post("/files/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """
    Upload a file to the sandbox.

    Multipart form: file field with the file to upload.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a name.")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=413, detail="File too large. Maximum 10 MB.")

    client = get_sandbox_client()

    # First upload to sandbox via the client's internal mechanism
    result = await client.upload_file(file.filename, content)

    return {
        "filename": file.filename,
        "size_bytes": len(content),
        "message": result,
    }


# ---------------------------------------------------------------------------
#  Stats / summary
# ---------------------------------------------------------------------------

@router.post("/stats")
async def sandbox_stats() -> dict:
    """
    Get a comprehensive sandbox status summary.
    Combines health, dependencies, and files.
    """
    client = get_sandbox_client()

    health = await client.health()
    deps = await client.list_dependencies()
    files = await client.list_files()

    return {
        "health": {
            "reachable": health.reachable,
            "latency_ms": health.latency_ms,
        },
        "dependencies": {
            "count": deps.count,
            "packages": deps.packages[:20],  # Top 20
        },
        "files": {
            "count": len(files),
            "names": files[:20],  # Top 20
        },
    }
