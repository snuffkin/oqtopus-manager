"""Routes for managing OQTOPUS environments."""

from __future__ import annotations

import logging
import pathlib
import shutil
from typing import TYPE_CHECKING, Annotated

import yaml
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from pydantic import ValidationError

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
from oqtopus_manager.util.cli import stream_log_tail, stream_oqtopus_init

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from oqtopus_manager.config import AppConfig

router = APIRouter(prefix="/backend", tags=["backend"])
logger = logging.getLogger(__name__)


@router.get("", response_class=HTMLResponse)
async def list_environments(request: Request) -> HTMLResponse:
    """Render the environments list page.

    Returns:
        HTMLResponse with the rendered environments list.

    """
    cfg = _get_config(request)
    all_envs = cfg.load_environments()
    environments = [e for e in all_envs if e.template == "backend"]
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
            "default_template": "backend",
        },
    )


@router.post("")
async def create_environment(
    request: Request,
    name: Annotated[str, Form()],
    template: Annotated[str, Form()],
    root_path: Annotated[str, Form()] = "",
) -> JSONResponse:
    """Validate the new environment request and return JSON.

    Returns ``{"ok": true}`` when validation passes so the client can
    proceed to open the SSE stream.  Returns an error JSON with the
    appropriate HTTP status on failure.

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

    logger.info("Environment '%s' validated (template=%s)", name, template)
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
            # Guard against duplicate entries if config was modified concurrently
            if not any(e.name == name for e in environments):
                resolved = new_env.resolved_root_path(cfg.default_environment_base_path)
                # Persist absolute path so the entry is cwd-independent
                env_to_save = new_env.model_copy(update={"root_path": resolved})
                environments.append(env_to_save)
                cfg.save_environments(environments)
                logger.info("Environment '%s' created and saved to config", name)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
            result[key.strip()] = value.strip()
    return result


def _build_list_context(environments: list[Environment], cfg: AppConfig) -> dict:
    """Build template context for the backend list page.

    Returns:
        Dict with env_items (list of dicts with env and all_installed) and base_path.

    """
    env_items = []
    for env in environments:
        resolved = env.resolved_root_path(cfg.default_environment_base_path)
        meta = _read_metadata(resolved)
        # All three service versions must be present for the env to be fully installed
        all_installed = bool(
            meta.get("engine_version")
            and meta.get("tranqu_version")
            and meta.get("gateway_version")
        )
        env_items.append({"env": env, "all_installed": all_installed})
    return {
        "env_items": env_items,
        "base_path": cfg.default_environment_base_path,
        "url_prefix": "/backend",
        "page_title": "Backend",
        "page_description": "Manage your OQTOPUS backend environments.",
        "has_device_status": True,
    }


def _components_installed(install_root: str) -> bool:
    """Return True if at least one component directory exists under install_root.

    Returns:
        True if at least one component directory is present.

    """
    root = pathlib.Path(install_root)
    return any((root / comp).is_dir() for comp in ("engine", "tranqu", "gateway"))


@router.get("/{name}/settings-partial", response_class=HTMLResponse)
async def get_settings_partial(request: Request, name: str) -> HTMLResponse:
    """Return the settings partial HTML for the given environment.

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
            "version_keys": ["engine_version", "tranqu_version", "gateway_version"],
        },
    )


@router.get("/{name}/services/{service}/config", response_class=HTMLResponse)
async def service_config(request: Request, name: str, service: str) -> HTMLResponse:
    """Render the service config editor page.

    Returns:
        HTMLResponse with the service config editor.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    config_dir = resolved / "config" / service

    def _read(path: pathlib.Path) -> str | None:
        return path.read_text(encoding="utf-8") if path.exists() else None

    config_locked, _, config_locked_since, config_locked_since_ts = _check_lock(
        config_dir / "config.yaml.lock", cfg.file_edit_lock_timeout_sec
    )
    logging_locked, _, logging_locked_since, logging_locked_since_ts = _check_lock(
        config_dir / "logging.yaml.lock", cfg.file_edit_lock_timeout_sec
    )

    return _get_templates(request).TemplateResponse(
        request,
        "environments/service_config.html",
        {
            "env": env,
            "service": service,
            "config_dir": config_dir,
            "config_content": _read(config_dir / "config.yaml"),
            "logging_content": _read(config_dir / "logging.yaml"),
            "config_is_locked": config_locked,
            "config_locked_since": config_locked_since,
            "config_locked_since_ts": config_locked_since_ts,
            "logging_is_locked": logging_locked,
            "logging_locked_since": logging_locked_since,
            "logging_locked_since_ts": logging_locked_since_ts,
            **_load_topology_context(service, resolved, cfg.file_edit_lock_timeout_sec),
            "lock_timeout_sec": cfg.file_edit_lock_timeout_sec,
        },
    )


def _read_path_from_yaml(
    yaml_file: pathlib.Path, keys: list[str], env_root: pathlib.Path
) -> pathlib.Path | None:
    """Read a file path from a YAML file by following a chain of keys.

    Returns:
        The resolved Path, or None if not found or on any parsing error.

    """
    if not yaml_file.exists():
        return None
    try:
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        value: object = data
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        if not value:
            return None
        path = pathlib.Path(str(value))
        # Resolve relative paths against env_root rather than the process cwd
        return path if path.is_absolute() else env_root / path
    except KeyError, TypeError, AttributeError:
        return None


def _get_log_file(env_root: pathlib.Path, service: str) -> pathlib.Path | None:
    """Return the log file path from the service logging.yaml, or None.

    Returns:
        The Path to the log file, or None if it cannot be determined.

    """
    return _read_path_from_yaml(
        env_root / "config" / service / "logging.yaml",
        ["handlers", "file", "filename"],
        env_root,
    )


def _get_topology_json_path(env_root: pathlib.Path) -> pathlib.Path | None:
    """Return device_topology_json_path from gateway config.yaml, or None.

    Returns:
        The resolved Path to the topology JSON file, or None if not configured.

    """
    return _read_path_from_yaml(
        env_root / "config" / "gateway" / "config.yaml",
        ["device_topology_json_path"],
        env_root,
    )


@router.get("/{name}/services/{service}/log", response_class=HTMLResponse)
async def service_log(request: Request, name: str, service: str) -> HTMLResponse:
    """Render the service log viewer page.

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
    """SSE endpoint: stream the service log file using tail.

    Returns:
        StreamingResponse with SSE-formatted log lines.

    Raises:
        HTTPException: If the log file is not found.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    log_file = _get_log_file(resolved, service)
    if log_file is None or not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found.")
    return StreamingResponse(
        stream_log_tail(log_file, cfg.log_tail_lines),
        media_type="text/event-stream",
    )


@router.get("/{name}/services/{service}/log/download")
async def service_log_download(
    request: Request, name: str, service: str
) -> FileResponse:
    """Download the service log file.

    Returns:
        FileResponse with the log file content.

    Raises:
        HTTPException: If the log file is not found.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    log_file = _get_log_file(resolved, service)
    if log_file is None or not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found.")
    return FileResponse(
        path=log_file,
        filename=log_file.name,
        media_type="text/plain",
    )


def _config_which_to_filename(which: str) -> str:
    if which not in {"config", "logging"}:
        raise HTTPException(status_code=400, detail=f"Unknown config type: {which!r}.")
    return f"{which}.yaml"


@router.post("/{name}/services/{service}/config/{which}/force-unlock")
async def force_unlock_service_config(
    request: Request, name: str, service: str, which: str
) -> JSONResponse:
    """Force-unlock a service config file.

    Returns:
        JSONResponse with ok=True on success.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    filename = _config_which_to_filename(which)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    return _force_unlock_file(resolved / "config" / service / f"{filename}.lock")


@router.post("/{name}/services/{service}/config/{which}/lock")
async def acquire_service_config_lock(
    request: Request, name: str, service: str, which: str
) -> JSONResponse:
    """Acquire a lock on a service config file.

    Returns:
        JSONResponse with ok=True and token on success, or conflict info.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    filename = _config_which_to_filename(which)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    lock_path = resolved / "config" / service / f"{filename}.lock"
    return _acquire_file_lock(lock_path, cfg.file_edit_lock_timeout_sec)


@router.post("/{name}/services/{service}/config/{which}/unlock")
async def release_service_config_lock(
    request: Request, name: str, service: str, which: str, body: _UnlockBody
) -> JSONResponse:
    """Release a lock on a service config file.

    Returns:
        JSONResponse with ok=True if the lock was released.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    filename = _config_which_to_filename(which)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    lock_path = resolved / "config" / service / f"{filename}.lock"
    return _release_file_lock(lock_path, body.token, cfg.file_edit_lock_timeout_sec)


@router.post("/{name}/services/{service}/config/{which}/save")
async def save_service_config(
    request: Request, name: str, service: str, which: str, body: _SaveBody
) -> JSONResponse:
    """Save a service config file after validating the lock token.

    Returns:
        JSONResponse with ok=True on success.

    """
    cfg = _get_config(request)
    env = _get_environment_or_404(name, cfg)
    filename = _config_which_to_filename(which)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    config_path = resolved / "config" / service / filename
    lock_path = resolved / "config" / service / f"{filename}.lock"
    return _save_file(
        config_path, lock_path, body.content, body.token, cfg.file_edit_lock_timeout_sec
    )


def _load_topology_context(service: str, resolved: pathlib.Path, timeout: int) -> dict:
    """Build topology JSON template context for the service config page.

    Returns:
        Dict with topology_json_path, topology_content, and lock state keys.

    """
    empty: dict = {
        "topology_json_path": None,
        "topology_content": None,
        "topology_is_locked": False,
        "topology_locked_since": None,
        "topology_locked_since_ts": None,
    }
    if service != "gateway":
        return empty
    path = _get_topology_json_path(resolved)
    if path is None:
        return empty
    content = path.read_text(encoding="utf-8") if path.exists() else None
    lock_path = path.parent / f"{path.name}.lock"
    is_locked, _, locked_since, locked_since_ts = _check_lock(lock_path, timeout)
    return {
        "topology_json_path": path,
        "topology_content": content,
        "topology_is_locked": is_locked,
        "topology_locked_since": locked_since,
        "topology_locked_since_ts": locked_since_ts,
    }


def _resolve_topology_path(name: str, cfg: AppConfig) -> pathlib.Path:
    """Look up the topology JSON path for a named environment.

    Returns:
        The resolved topology JSON file Path.

    Raises:
        HTTPException: If environment not found or topology path not configured.

    """
    env = _get_environment_or_404(name, cfg)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    path = _get_topology_json_path(resolved)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail="device_topology_json_path not configured in gateway config.",
        )
    return path


@router.post("/{name}/gateway/topology-json/force-unlock")
async def force_unlock_gateway_topology_json(
    request: Request, name: str
) -> JSONResponse:
    """Force-unlock the gateway device topology JSON file.

    Returns:
        JSONResponse with ok=True on success.

    """
    cfg = _get_config(request)
    path = _resolve_topology_path(name, cfg)
    return _force_unlock_file(path.parent / f"{path.name}.lock")


@router.post("/{name}/gateway/topology-json/lock")
async def acquire_gateway_topology_json_lock(
    request: Request, name: str
) -> JSONResponse:
    """Acquire a lock on the gateway device topology JSON file.

    Returns:
        JSONResponse with ok=True and token on success, or conflict info.

    """
    cfg = _get_config(request)
    path = _resolve_topology_path(name, cfg)
    lock_path = path.parent / f"{path.name}.lock"
    return _acquire_file_lock(lock_path, cfg.file_edit_lock_timeout_sec)


@router.post("/{name}/gateway/topology-json/unlock")
async def release_gateway_topology_json_lock(
    request: Request, name: str, body: _UnlockBody
) -> JSONResponse:
    """Release the lock on the gateway device topology JSON file.

    Returns:
        JSONResponse with ok=True if the lock was released.

    """
    cfg = _get_config(request)
    path = _resolve_topology_path(name, cfg)
    lock_path = path.parent / f"{path.name}.lock"
    return _release_file_lock(lock_path, body.token, cfg.file_edit_lock_timeout_sec)


@router.post("/{name}/gateway/topology-json/save")
async def save_gateway_topology_json(
    request: Request, name: str, body: _SaveBody
) -> JSONResponse:
    """Save the gateway device topology JSON file after validating the lock token.

    Returns:
        JSONResponse with ok=True on success.

    """
    cfg = _get_config(request)
    path = _resolve_topology_path(name, cfg)
    lock_path = path.parent / f"{path.name}.lock"
    return _save_file(
        path, lock_path, body.content, body.token, cfg.file_edit_lock_timeout_sec
    )


@router.get("/{name}/gateway/topology-json/download")
async def gateway_topology_json_download(request: Request, name: str) -> FileResponse:
    """Download the gateway device topology JSON file.

    Returns:
        FileResponse with the topology JSON content.

    Raises:
        HTTPException: If the topology file is not found.

    """
    cfg = _get_config(request)
    path = _resolve_topology_path(name, cfg)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Topology JSON file not found.")
    return FileResponse(path=path, filename=path.name, media_type="application/json")


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
    """Download the .env file for an environment.

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
    """Render the .env editor page for an environment.

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


@router.get("/{name}", response_class=HTMLResponse)
async def get_environment(request: Request, name: str) -> HTMLResponse:
    """Render the environment detail page.

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
            meta.get("engine_version")
            and meta.get("tranqu_version")
            and meta.get("gateway_version")
        ),
        "version_keys": ["engine_version", "tranqu_version", "gateway_version"],
    }
    return _get_templates(request).TemplateResponse(
        request, "environments/backend_detail.html", ctx
    )


@router.delete("/{name}", response_class=HTMLResponse)
async def delete_environment(request: Request, name: str) -> HTMLResponse:
    """Delete an environment and its directory.

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
    logger.info("Deleting environment '%s' (root=%s)", name, root_dir)
    if root_dir.exists():
        shutil.rmtree(root_dir)
        logger.info("Deleted directory: %s", root_dir)

    remaining = [e for e in environments if e.name != name]
    cfg.save_environments(remaining)

    backend_remaining = [e for e in remaining if e.template == "backend"]
    return _get_templates(request).TemplateResponse(
        request,
        "environments/list.html",
        _build_list_context(backend_remaining, cfg),
    )
