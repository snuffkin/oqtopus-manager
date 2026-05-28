"""SSE endpoint for executing oqtopus backend subcommands."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from oqtopus_manager.cli import stream_oqtopus_backend
from oqtopus_manager.config import AppConfig

router = APIRouter(prefix="/environments", tags=["backend"])

_VALID_SERVICES = frozenset(
    {"all", "core", "sse_engine", "mitigator", "estimator", "combiner", "tranqu", "gateway"}
)
_VALID_COMPONENTS = frozenset({"engine", "tranqu", "gateway"})
_VALID_STATUSES = frozenset({"active", "inactive", "maintenance"})


def _get_config(request: Request) -> AppConfig:
    return request.app.state.config


def _build_args(
    cmd: str,
    service: str,
    component: str,
    version: str,
    foreground: bool,
    status: str,
    skip_sse_build: bool,
) -> list[str]:
    """Translate validated query params into oqtopus backend argv."""
    if cmd == "status":
        return ["status"]
    if cmd == "info":
        return ["info"]
    if cmd in {"start", "stop", "restart"}:
        if service not in _VALID_SERVICES:
            raise ValueError(f"Invalid service '{service}'")
        args = [cmd, service]
        if cmd == "start" and foreground:
            args.append("--foreground")
        return args
    if cmd == "versions":
        if component not in _VALID_COMPONENTS:
            raise ValueError(f"Invalid component '{component}'")
        return ["versions", component]
    if cmd == "install":
        comp = component if component in _VALID_COMPONENTS else None
        if comp is None and component != "all":
            raise ValueError(f"Invalid component '{component}'")
        args = ["install", component]
        if component != "all" and version:
            args.append(version)
        if skip_sse_build:
            args.append("--skip-sse-build")
        return args
    if cmd == "update":
        if component not in _VALID_COMPONENTS:
            raise ValueError(f"Invalid component '{component}'")
        return ["update", component]
    if cmd == "uninstall":
        if component not in _VALID_COMPONENTS:
            raise ValueError(f"Invalid component '{component}'")
        if not version:
            raise ValueError("version is required for uninstall")
        return ["uninstall", component, version]
    if cmd == "build":
        return ["build", "sse-runtime"]
    if cmd == "device-status-show":
        return ["device-status", "show"]
    if cmd == "device-status-set":
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'")
        return ["device-status", status]
    raise ValueError(f"Unknown command '{cmd}'")


@router.get("/{name}/backend/stream")
async def backend_stream(
    request: Request,
    name: str,
    cmd: str,
    service: str = "all",
    component: str = "engine",
    version: str = "",
    foreground: bool = False,
    status: str = "",
    skip_sse_build: bool = False,
) -> StreamingResponse:
    """SSE endpoint: run an oqtopus backend subcommand and stream its output."""
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")

    try:
        backend_args = _build_args(cmd, service, component, version, foreground, status, skip_sse_build)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    cwd = env.resolved_root_path(cfg.default_environment_base_path)

    async def event_stream():
        async for chunk in stream_oqtopus_backend(backend_args, cwd):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")
