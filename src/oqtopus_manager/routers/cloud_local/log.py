"""Routes for the cloud-local service log viewer, stream, and download."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from oqtopus_manager.routers._utils import (
    _get_config,
    _get_environment_or_404,
    _get_templates,
)
from oqtopus_manager.routers.cloud_local._utils import _get_log_file
from oqtopus_manager.util.cli import stream_log_tail

router = APIRouter(prefix="/cloud-local", tags=["cloud-local"])


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
