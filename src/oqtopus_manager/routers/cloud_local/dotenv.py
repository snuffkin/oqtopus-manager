"""Routes for the cloud-local .env file editor (view, lock, save, download)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

if TYPE_CHECKING:
    import pathlib
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from oqtopus_manager.routers._file_edit import (
    _acquire_file_lock,
    _check_lock,
    _force_unlock_file,
    _release_file_lock,
    _save_file,
    _SaveBody,
    _UnlockBody,
)
from oqtopus_manager.routers._utils import (
    _get_config,
    _get_environment_or_404,
    _get_templates,
)

router = APIRouter(prefix="/cloud-local", tags=["cloud-local"])


@router.post("/{name}/dotenv/force-unlock")
async def force_unlock_dotenv(request: Request, name: str) -> JSONResponse:
    """Force-unlock the .env file.

    Returns:
        JSONResponse with ok=True on success.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    return _force_unlock_file(resolved / "config" / ".env.lock")


@router.post("/{name}/dotenv/lock")
async def acquire_dotenv_lock(request: Request, name: str) -> JSONResponse:
    """Acquire a lock on the .env file.

    Returns:
        JSONResponse with ok=True and token on success, or conflict info.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    return _acquire_file_lock(
        resolved / "config" / ".env.lock", cfg.file_edit_lock_timeout_sec
    )


@router.post("/{name}/dotenv/unlock")
async def release_dotenv_lock(
    request: Request, name: str, body: _UnlockBody
) -> JSONResponse:
    """Release the lock on the .env file.

    Returns:
        JSONResponse with ok=True if the lock was released.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    return _release_file_lock(
        resolved / "config" / ".env.lock", body.token, cfg.file_edit_lock_timeout_sec
    )


@router.post("/{name}/dotenv/save")
async def save_dotenv(request: Request, name: str, body: _SaveBody) -> JSONResponse:
    """Save the .env file after validating the lock token.

    Returns:
        JSONResponse with ok=True on success.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    dotenv_path = resolved / "config" / ".env"
    lock_path = resolved / "config" / ".env.lock"
    return _save_file(
        dotenv_path, lock_path, body.content, body.token, cfg.file_edit_lock_timeout_sec
    )


@router.get("/{name}/dotenv/download")
async def environment_dotenv_download(request: Request, name: str) -> FileResponse:
    """Download the .env file for a cloud-local environment.

    Returns:
        FileResponse with the .env file content.

    Raises:
        HTTPException: If the .env file is not found.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    dotenv_path = (
        env.resolved_root_path(cfg.default_environment_base_path) / "config" / ".env"
    )
    if not dotenv_path.exists():
        raise HTTPException(status_code=404, detail="config/.env not found.")
    return FileResponse(path=dotenv_path, filename=".env", media_type="text/plain")


@router.get("/{name}/dotenv", response_class=HTMLResponse)
async def environment_dotenv(request: Request, name: str) -> HTMLResponse:
    """Render the .env editor page for a cloud-local environment.

    Returns:
        HTMLResponse with the .env editor page.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    dotenv_path = resolved / "config" / ".env"
    lock_path = resolved / "config" / ".env.lock"

    def _read(path: pathlib.Path) -> str | None:
        return path.read_text(encoding="utf-8") if path.exists() else None

    is_locked, _, locked_since, locked_since_ts = _check_lock(
        lock_path, cfg.file_edit_lock_timeout_sec
    )

    return _get_templates(request).TemplateResponse(
        request,
        "environments/dotenv.html",
        {
            "env": env,
            "dotenv_path": dotenv_path,
            "dotenv_content": _read(dotenv_path),
            "is_locked": is_locked,
            "locked_since": locked_since,
            "locked_since_ts": locked_since_ts,
            "lock_timeout_sec": cfg.file_edit_lock_timeout_sec,
        },
    )
