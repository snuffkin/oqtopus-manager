"""Routes for managing OQTOPUS cloud-local environments."""

from __future__ import annotations

import logging
import pathlib
import shutil
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from pydantic import ValidationError

from oqtopus_manager.cli import stream_log_tail, stream_oqtopus_init
from oqtopus_manager.models.environment import Environment
from oqtopus_manager.routers._file_edit import (
    _acquire_file_lock,
    _check_lock,
    _force_unlock_file,
    _release_file_lock,
    _save_file,
    _SaveBody,
    _UnlockBody,
)
from oqtopus_manager.routers._shared import (
    _get_config,
    _get_environment_or_404,
    _get_templates,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from oqtopus_manager.config import AppConfig

router = APIRouter(prefix="/cloud-local", tags=["cloud-local"])
logger = logging.getLogger(__name__)

_VERSION_KEYS = ["cloud_version", "frontend_version", "admin_version"]


def _read_metadata(env_root: pathlib.Path) -> dict[str, str]:
    """Parse <env_root>/.metadata (key=value lines) into a dict.

    Returns:
        Dict mapping key strings to value strings.

    """
    path = env_root / ".metadata"
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip().removeprefix("cloud_local_")] = value.strip()
    return result


def _build_list_context(environments: list[Environment], cfg: AppConfig) -> dict:
    """Build template context for the cloud-local list page.

    Returns:
        Dict with env_items and metadata for the list template.

    """
    env_items = []
    for env in environments:
        resolved = env.resolved_root_path(cfg.default_environment_base_path)
        meta = _read_metadata(resolved)
        all_installed = bool(
            meta.get("cloud_version")
            and meta.get("frontend_version")
            and meta.get("admin_version")
        )
        env_items.append({"env": env, "all_installed": all_installed})
    return {
        "env_items": env_items,
        "base_path": cfg.default_environment_base_path,
        "url_prefix": "/cloud-local",
        "page_title": "Cloud Local",
        "page_description": "Manage your OQTOPUS cloud-local environments.",
        "has_device_status": False,
    }


def _get_log_file(env_root: pathlib.Path, service: str) -> pathlib.Path:
    """Return the log file path for a cloud-local service.

    Returns:
        Path to logs/<service>/service.log under env_root.

    """
    return env_root / "logs" / service / "service.log"


@router.get("", response_class=HTMLResponse)
async def list_environments(request: Request) -> HTMLResponse:
    """Render the cloud-local environments list page.

    Returns:
        HTMLResponse with the rendered environments list.

    """
    cfg = _get_config(request)
    all_envs = cfg.load_environments()
    environments = [e for e in all_envs if e.template == "cloud-local"]
    return _get_templates(request).TemplateResponse(
        request,
        "environments/list.html",
        _build_list_context(environments, cfg),
    )


@router.get("/new", response_class=HTMLResponse)
async def new_environment_form(request: Request) -> HTMLResponse:
    """Render the new environment form.

    Returns:
        HTMLResponse with the rendered new environment form.

    """
    cfg = _get_config(request)
    return _get_templates(request).TemplateResponse(
        request,
        "environments/new.html",
        {
            "default_browse_path": cfg.default_environment_base_path,
            "default_template": "cloud-local",
        },
    )


@router.post("")
async def create_environment(
    request: Request,
    name: Annotated[str, Form()],
    template: Annotated[str, Form()],
    root_path: Annotated[str, Form()] = "",
) -> JSONResponse:
    """Validate the new cloud-local environment request and return JSON.

    Returns:
        JSONResponse indicating success or failure.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()

    if any(e.name == name for e in environments):
        return JSONResponse(
            {"ok": False, "error": f"Environment '{name}' already exists."},
            status_code=409,
        )

    try:
        Environment(
            name=name,
            template=template,
            root_path=pathlib.Path(root_path) if root_path.strip() else None,
        )
    except ValidationError as exc:
        return JSONResponse(
            {"ok": False, "error": exc.errors()[0]["msg"]},
            status_code=422,
        )

    logger.info("Cloud-local environment '%s' validated", name)
    return JSONResponse({"ok": True})


@router.get("/stream")
async def stream_environment_init(
    request: Request,
    name: str,
    template: str,
    root_path: str = "",
) -> StreamingResponse:
    """SSE endpoint: run oqtopus init and stream output line by line.

    Returns:
        StreamingResponse with SSE-formatted output.

    """
    cfg = _get_config(request)

    new_env = Environment(
        name=name,
        template=template,
        root_path=pathlib.Path(root_path) if root_path.strip() else None,
    )
    parent_dir = new_env.resolved_root_path(cfg.default_environment_base_path).parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    async def event_stream() -> AsyncGenerator[str]:
        success = False
        async for chunk in stream_oqtopus_init(
            name=name, template=template, cwd=parent_dir
        ):
            yield chunk
            if "event: done\ndata: success" in chunk:
                success = True

        if success:
            environments = cfg.load_environments()
            if not any(e.name == name for e in environments):
                resolved = new_env.resolved_root_path(cfg.default_environment_base_path)
                env_to_save = new_env.model_copy(update={"root_path": resolved})
                environments.append(env_to_save)
                cfg.save_environments(environments)
                logger.info("Cloud-local environment '%s' created and saved", name)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{name}/settings-partial", response_class=HTMLResponse)
async def get_settings_partial(request: Request, name: str) -> HTMLResponse:
    """Return the settings partial HTML for the given cloud-local environment.

    Returns:
        HTMLResponse with the settings partial template.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    meta = _read_metadata(resolved)
    return _get_templates(request).TemplateResponse(
        request,
        "environments/_settings_dl.html",
        {
            "meta": meta,
            "resolved_root_path": resolved,
            "version_keys": _VERSION_KEYS,
        },
    )


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


@router.get("/{name}/services/{service}/log", response_class=HTMLResponse)
async def service_log(request: Request, name: str, service: str) -> HTMLResponse:
    """Render the service log viewer page for a cloud-local service.

    Returns:
        HTMLResponse with the log viewer page.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    log_file = _get_log_file(resolved, service)
    return _get_templates(request).TemplateResponse(
        request,
        "environments/service_log.html",
        {
            "env": env,
            "service": service,
            "log_file": log_file,
            "buffer_lines": cfg.log_buffer_lines,
        },
    )


@router.get("/{name}/services/{service}/log/stream")
async def service_log_stream(
    request: Request, name: str, service: str
) -> StreamingResponse:
    """SSE endpoint: stream the cloud-local service log file using tail.

    Returns:
        StreamingResponse with SSE-formatted log lines.

    Raises:
        HTTPException: If the log file is not found.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    log_file = _get_log_file(resolved, service)
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found.")
    return StreamingResponse(
        stream_log_tail(log_file, cfg.log_tail_lines),
        media_type="text/event-stream",
    )


@router.get("/{name}/services/{service}/log/download")
async def service_log_download(
    request: Request, name: str, service: str
) -> FileResponse:
    """Download the service log file for a cloud-local service.

    Returns:
        FileResponse with the log file content.

    Raises:
        HTTPException: If the log file is not found.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    log_file = _get_log_file(resolved, service)
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found.")
    return FileResponse(
        path=log_file,
        filename=log_file.name,
        media_type="text/plain",
    )


@router.get("/{name}", response_class=HTMLResponse)
async def get_environment(request: Request, name: str) -> HTMLResponse:
    """Render the cloud-local environment detail page.

    Returns:
        HTMLResponse with the environment detail page.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    meta = _read_metadata(resolved)
    ctx: dict = {
        "env": env,
        "resolved_root_path": resolved,
        "meta": meta,
        "all_versions_installed": bool(
            meta.get("cloud_version")
            and meta.get("frontend_version")
            and meta.get("admin_version")
        ),
        "version_keys": _VERSION_KEYS,
    }
    return _get_templates(request).TemplateResponse(
        request, "environments/cloud_local_detail.html", ctx
    )


@router.delete("/{name}", response_class=HTMLResponse)
async def delete_environment(request: Request, name: str) -> HTMLResponse:
    """Delete a cloud-local environment and its directory.

    Returns:
        HTMLResponse with the updated environments list.

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    target = next((e for e in environments if e.name == name), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")

    root_dir = target.resolved_root_path(cfg.default_environment_base_path)
    logger.info("Deleting cloud-local environment '%s' (root=%s)", name, root_dir)
    if root_dir.exists():
        shutil.rmtree(root_dir)
        logger.info("Deleted directory: %s", root_dir)

    remaining = [e for e in environments if e.name != name]
    cfg.save_environments(remaining)

    cl_remaining = [e for e in remaining if e.template == "cloud-local"]
    return _get_templates(request).TemplateResponse(
        request,
        "environments/list.html",
        _build_list_context(cl_remaining, cfg),
    )
