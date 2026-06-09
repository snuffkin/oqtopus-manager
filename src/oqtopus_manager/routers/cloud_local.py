"""SSE endpoint for executing oqtopus cloud-local subcommands."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from oqtopus_manager.routers._shared import _get_config, _get_environment_or_404
from oqtopus_manager.util.cli import (
    run_oqtopus_subcommand_output,
    stream_oqtopus_subcommand,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

router = APIRouter(prefix="/cloud-local", tags=["cloud-local"])
logger = logging.getLogger(__name__)

_SUBCOMMAND = "cloud-local"
_VALID_SERVICES = frozenset({
    "all",
    "db",
    "worker",
    "user_signup",
    "admin",
    "provider",
    "user",
})
_VALID_COMPONENTS = frozenset({"cloud", "frontend", "admin"})
_SERVICE_CMDS = frozenset({"start", "stop", "restart"})
_COMPONENT_CMDS = frozenset({"versions", "install", "update", "uninstall"})


def _validate_component(component: str, *, allow_all: bool = False) -> None:
    valid = _VALID_COMPONENTS | {"all"} if allow_all else _VALID_COMPONENTS
    if component not in valid:
        msg = f"Invalid component '{component}'"
        raise ValueError(msg)


def _build_service_args(
    cmd: str,
    service: str,
    foreground: bool,  # noqa: FBT001
) -> list[str]:
    if service not in _VALID_SERVICES:
        msg = f"Invalid service '{service}'"
        raise ValueError(msg)
    args = [cmd, service]
    if cmd == "start" and foreground:
        args.append("--foreground")
    return args


def _build_component_args(cmd: str, component: str, version: str) -> list[str]:
    if cmd == "versions":
        _validate_component(component)
        return ["versions", component]
    if cmd == "install":
        _validate_component(component, allow_all=True)
        args = ["install", component]
        if component != "all" and version:
            args.append(version)
        return args
    if cmd == "update":
        _validate_component(component)
        return ["update", component]
    _validate_component(component)
    if not version:
        msg = "version is required for uninstall"
        raise ValueError(msg)
    return ["uninstall", component, version]


def _build_args(
    cmd: str,
    service: str,
    component: str,
    version: str,
    foreground: bool,  # noqa: FBT001
) -> list[str]:
    """Translate validated query params into oqtopus cloud-local argv.

    Returns:
        List of string arguments to pass to the oqtopus cloud-local CLI.

    Raises:
        ValueError: If an invalid service, component, or command is provided.

    """
    if cmd in {"status", "info"}:
        return [cmd]
    if cmd in _SERVICE_CMDS:
        return _build_service_args(cmd, service, foreground)
    if cmd in _COMPONENT_CMDS:
        return _build_component_args(cmd, component, version)
    msg = f"Unknown command '{cmd}'"
    raise ValueError(msg)


@dataclass
class _StreamParams:
    cmd: str
    service: str = "all"
    component: str = "cloud"
    version: str = ""
    foreground: bool = False


@router.get("/{name}/component-versions")
async def component_versions_list(
    request: Request,
    name: str,
    component: str,
) -> JSONResponse:
    """Run oqtopus cloud-local versions <component> and return parsed version list.

    Returns:
        JSONResponse with a list of version strings.

    Raises:
        HTTPException: If the component is invalid or environment is not found.

    """
    if component not in _VALID_COMPONENTS:
        raise HTTPException(status_code=400, detail=f"Invalid component '{component}'")

    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)

    cwd = env.resolved_root_path(cfg.default_environment_base_path)
    output = await run_oqtopus_subcommand_output(
        _SUBCOMMAND, ["versions", component], cwd
    )

    versions = [
        m.group()
        for line in output.splitlines()
        if (m := re.search(r"branch:\S+|v\d+[\w.+-]*", line))
    ]
    return JSONResponse({"versions": versions})


@router.get("/{name}/stream")
async def cloud_local_stream(
    request: Request,
    name: str,
    params: Annotated[_StreamParams, Depends()],
) -> StreamingResponse:
    """SSE endpoint: run an oqtopus cloud-local subcommand and stream its output.

    Returns:
        StreamingResponse with SSE-formatted output from the cloud-local command.

    Raises:
        HTTPException: If the environment is not found or command arguments are invalid.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)

    try:
        args = _build_args(
            params.cmd,
            params.service,
            params.component,
            params.version,
            params.foreground,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cwd = env.resolved_root_path(cfg.default_environment_base_path)
    logger.info("Cloud-local stream: cmd=%s args=%s env=%s", params.cmd, args, name)

    async def event_stream() -> AsyncGenerator[str]:
        async for chunk in stream_oqtopus_subcommand(_SUBCOMMAND, args, cwd):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")
