"""Routes for managing OQTOPUS environments."""

from __future__ import annotations

import datetime
import pathlib
import shutil
import time
import uuid
from typing import TYPE_CHECKING, Annotated

import yaml
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from pydantic import BaseModel, ValidationError

from oqtopus_manager.cli import stream_log_tail, stream_oqtopus_init
from oqtopus_manager.models.environment import Environment

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastapi.templating import Jinja2Templates

    from oqtopus_manager.config import AppConfig

router = APIRouter(prefix="/environments", tags=["environments"])


def _get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def _get_config(request: Request) -> AppConfig:
    return request.app.state.config


@router.get("", response_class=HTMLResponse)
async def list_environments(request: Request) -> HTMLResponse:
    """Render the environments list page.

    Returns:
        HTMLResponse with the rendered environments list.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    return _get_templates(request).TemplateResponse(
        request,
        "environments/list.html",
        {"environments": environments, "base_path": cfg.default_environment_base_path},
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
        {"default_browse_path": cfg.default_environment_base_path},
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

    return StreamingResponse(event_stream(), media_type="text/event-stream")


_DETAIL_TEMPLATE: dict[str, str] = {
    "backend": "environments/backend_detail.html",
}


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

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    meta = _read_metadata(resolved)
    return _get_templates(request).TemplateResponse(
        request,
        "environments/_settings_dl.html",
        {"meta": meta, "resolved_root_path": resolved},
    )


@router.get("/{name}/services/{service}/config", response_class=HTMLResponse)
async def service_config(request: Request, name: str, service: str) -> HTMLResponse:
    """Render the service config editor page.

    Returns:
        HTMLResponse with the service config editor.

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
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
            "lock_timeout_sec": cfg.file_edit_lock_timeout_sec,
        },
    )


def _get_log_file(env_root: pathlib.Path, service: str) -> pathlib.Path | None:
    """Return the log file path from the service logging.yaml, or None.

    Returns:
        The Path to the log file, or None if it cannot be determined.

    """
    logging_yaml = env_root / "config" / service / "logging.yaml"
    if not logging_yaml.exists():
        return None
    try:
        data = yaml.safe_load(logging_yaml.read_text(encoding="utf-8"))
        filename = data["handlers"]["file"]["filename"]
        path = pathlib.Path(filename)
        return path if path.is_absolute() else env_root / path
    except KeyError, TypeError, AttributeError:
        return None


@router.get("/{name}/services/{service}/log", response_class=HTMLResponse)
async def service_log(request: Request, name: str, service: str) -> HTMLResponse:
    """Render the service log viewer page.

    Returns:
        HTMLResponse with the log viewer page.

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
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
        HTTPException: If the environment or log file is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
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
        HTTPException: If the environment or log file is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    log_file = _get_log_file(resolved, service)
    if log_file is None or not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found.")
    return FileResponse(
        path=log_file,
        filename=log_file.name,
        media_type="text/plain",
    )


class _UnlockBody(BaseModel):
    token: str


class _SaveBody(BaseModel):
    token: str
    content: str


def _check_lock(
    lock_path: pathlib.Path, timeout: int
) -> tuple[bool, str | None, str | None, float | None]:
    """Return (is_locked, token_if_locked, locked_since_str, locked_since_ts).

    Removes stale lock files automatically.

    Returns:
        Tuple of (is_locked, token, locked_since, locked_since_ts).

    """
    if not lock_path.exists():
        return False, None, None, None
    try:
        parts = lock_path.read_text(encoding="utf-8").strip().split("\n", 1)
        token = parts[0]
        ts = float(parts[1]) if len(parts) > 1 else 0.0
        if time.time() - ts < timeout:
            locked_since = datetime.datetime.fromtimestamp(
                ts, tz=datetime.UTC
            ).strftime("%Y-%m-%d %H:%M:%S")
            return True, token, locked_since, ts
        lock_path.unlink(missing_ok=True)
    except ValueError, OSError:
        lock_path.unlink(missing_ok=True)
    return False, None, None, None


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

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    filename = _config_which_to_filename(which)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    (resolved / "config" / service / f"{filename}.lock").unlink(missing_ok=True)
    return JSONResponse({"ok": True})


@router.post("/{name}/services/{service}/config/{which}/lock")
async def acquire_service_config_lock(
    request: Request, name: str, service: str, which: str
) -> JSONResponse:
    """Acquire a lock on a service config file.

    Returns:
        JSONResponse with ok=True and token on success, or conflict info.

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    filename = _config_which_to_filename(which)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    lock_path = resolved / "config" / service / f"{filename}.lock"
    is_locked, _, locked_since, locked_since_ts = _check_lock(
        lock_path, cfg.file_edit_lock_timeout_sec
    )
    if is_locked:
        return JSONResponse(
            {
                "ok": False,
                "locked_since": locked_since,
                "locked_since_ts": locked_since_ts,
            },
            status_code=409,
        )
    ts = time.time()
    token = str(uuid.uuid4())
    lock_path.write_text(f"{token}\n{ts}", encoding="utf-8")
    return JSONResponse({"ok": True, "token": token, "acquired_ts": ts})


@router.post("/{name}/services/{service}/config/{which}/unlock")
async def release_service_config_lock(
    request: Request, name: str, service: str, which: str, body: _UnlockBody
) -> JSONResponse:
    """Release a lock on a service config file.

    Returns:
        JSONResponse with ok=True if the lock was released.

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    filename = _config_which_to_filename(which)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    lock_path = resolved / "config" / service / f"{filename}.lock"
    is_locked, token, _, __ = _check_lock(lock_path, cfg.file_edit_lock_timeout_sec)
    if is_locked and token == body.token:
        lock_path.unlink(missing_ok=True)
        return JSONResponse({"ok": True})
    return JSONResponse(
        {"ok": False, "error": "Lock not held or token mismatch."}, status_code=403
    )


@router.post("/{name}/services/{service}/config/{which}/save")
async def save_service_config(
    request: Request, name: str, service: str, which: str, body: _SaveBody
) -> JSONResponse:
    """Save a service config file after validating the lock token.

    Returns:
        JSONResponse with ok=True on success.

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    filename = _config_which_to_filename(which)
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    config_path = resolved / "config" / service / filename
    lock_path = resolved / "config" / service / f"{filename}.lock"
    is_locked, token, _, __ = _check_lock(lock_path, cfg.file_edit_lock_timeout_sec)
    if not is_locked:
        return JSONResponse({"ok": False, "error": "Lock expired."}, status_code=409)
    if token != body.token:
        return JSONResponse({"ok": False, "error": "Invalid token."}, status_code=403)
    if config_path.exists():
        backup_ts = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d%H%M%S")
        shutil.copy2(config_path, config_path.parent / f"{filename}.{backup_ts}")
    config_path.write_text(body.content, encoding="utf-8")
    lock_path.unlink(missing_ok=True)
    return JSONResponse({"ok": True})


@router.post("/{name}/dotenv/force-unlock")
async def force_unlock_dotenv(request: Request, name: str) -> JSONResponse:
    """Force-unlock the .env file.

    Returns:
        JSONResponse with ok=True on success.

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    lock_path = resolved / "config" / ".env.lock"
    lock_path.unlink(missing_ok=True)
    return JSONResponse({"ok": True})


@router.post("/{name}/dotenv/lock")
async def acquire_dotenv_lock(request: Request, name: str) -> JSONResponse:
    """Acquire a lock on the .env file.

    Returns:
        JSONResponse with ok=True and token on success, or conflict info.

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    lock_path = resolved / "config" / ".env.lock"

    is_locked, _, locked_since, locked_since_ts = _check_lock(
        lock_path, cfg.file_edit_lock_timeout_sec
    )
    if is_locked:
        return JSONResponse(
            {
                "ok": False,
                "locked_since": locked_since,
                "locked_since_ts": locked_since_ts,
            },
            status_code=409,
        )

    ts = time.time()
    token = str(uuid.uuid4())
    lock_path.write_text(f"{token}\n{ts}", encoding="utf-8")
    return JSONResponse({"ok": True, "token": token, "acquired_ts": ts})


@router.post("/{name}/dotenv/unlock")
async def release_dotenv_lock(
    request: Request, name: str, body: _UnlockBody
) -> JSONResponse:
    """Release the lock on the .env file.

    Returns:
        JSONResponse with ok=True if the lock was released.

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    lock_path = resolved / "config" / ".env.lock"

    is_locked, token, _, __ = _check_lock(lock_path, cfg.file_edit_lock_timeout_sec)
    if is_locked and token == body.token:
        lock_path.unlink(missing_ok=True)
        return JSONResponse({"ok": True})
    return JSONResponse(
        {"ok": False, "error": "Lock not held or token mismatch."}, status_code=403
    )


@router.post("/{name}/dotenv/save")
async def save_dotenv(request: Request, name: str, body: _SaveBody) -> JSONResponse:
    """Save the .env file after validating the lock token.

    Returns:
        JSONResponse with ok=True on success.

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    lock_path = resolved / "config" / ".env.lock"
    dotenv_path = resolved / "config" / ".env"

    is_locked, token, _, __ = _check_lock(lock_path, cfg.file_edit_lock_timeout_sec)
    if not is_locked:
        return JSONResponse({"ok": False, "error": "Lock expired."}, status_code=409)
    if token != body.token:
        return JSONResponse({"ok": False, "error": "Invalid token."}, status_code=403)

    if dotenv_path.exists():
        backup_ts = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d%H%M%S")
        shutil.copy2(dotenv_path, dotenv_path.parent / f".env.{backup_ts}")

    dotenv_path.write_text(body.content, encoding="utf-8")
    lock_path.unlink(missing_ok=True)
    return JSONResponse({"ok": True})


@router.get("/{name}/dotenv/download")
async def environment_dotenv_download(request: Request, name: str) -> FileResponse:
    """Download the .env file for an environment.

    Returns:
        FileResponse with the .env file content.

    Raises:
        HTTPException: If the environment or .env file is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
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

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
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

    Raises:
        HTTPException: If the environment is not found.

    """
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    template_name = _DETAIL_TEMPLATE.get(env.template, "environments/detail.html")
    ctx: dict = {"env": env, "resolved_root_path": resolved}
    if env.template == "backend":
        meta = _read_metadata(resolved)
        ctx["meta"] = meta
        ctx["all_versions_installed"] = bool(
            meta.get("engine_version")
            and meta.get("tranqu_version")
            and meta.get("gateway_version")
        )
    return _get_templates(request).TemplateResponse(request, template_name, ctx)


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
    if root_dir.exists():
        shutil.rmtree(root_dir)

    remaining = [e for e in environments if e.name != name]
    cfg.save_environments(remaining)

    return _get_templates(request).TemplateResponse(
        request,
        "environments/list.html",
        {"environments": remaining, "base_path": cfg.default_environment_base_path},
    )
