"""Routes for managing OQTOPUS environments."""

import pathlib
import shutil
import time
import uuid
from datetime import datetime

import yaml
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError

from oqtopus_manager.cli import stream_log_tail, stream_oqtopus_init
from oqtopus_manager.config import AppConfig
from oqtopus_manager.models.environment import Environment

router = APIRouter(prefix="/environments", tags=["environments"])


def _get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def _get_config(request: Request) -> AppConfig:
    return request.app.state.config


@router.get("", response_class=HTMLResponse)
async def list_environments(request: Request) -> HTMLResponse:
    cfg = _get_config(request)
    environments = cfg.load_environments()
    return _get_templates(request).TemplateResponse(
        request,
        "environments/list.html",
        {"environments": environments, "base_path": cfg.default_environment_base_path},
    )


@router.get("/new", response_class=HTMLResponse)
async def new_environment_form(request: Request) -> HTMLResponse:
    cfg = _get_config(request)
    return _get_templates(request).TemplateResponse(
        request, "environments/new.html",
        {"default_browse_path": cfg.default_environment_base_path},
    )


@router.post("")
async def create_environment(
    request: Request,
    name: str = Form(...),
    template: str = Form(...),
    root_path: str = Form(""),
) -> JSONResponse:
    """Validate the new environment request and return JSON.

    Returns ``{"ok": true}`` when validation passes so the client can
    proceed to open the SSE stream.  Returns an error JSON with the
    appropriate HTTP status on failure.
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
    """SSE endpoint: run oqtopus init and stream output line by line."""
    cfg = _get_config(request)

    new_env = Environment(
        name=name,
        template=template,
        root_path=pathlib.Path(root_path) if root_path.strip() else None,
    )
    parent_dir = new_env.resolved_root_path(cfg.default_environment_base_path).parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    async def event_stream():
        success = False
        async for chunk in stream_oqtopus_init(name=name, template=template, cwd=parent_dir):
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
    """Parse <env_root>/.metadata (key=value lines) into a dict."""
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
    """Return True if at least one component directory exists under install_root."""
    root = pathlib.Path(install_root)
    return any((root / comp).is_dir() for comp in ("engine", "tranqu", "gateway"))


@router.get("/{name}/settings-partial", response_class=HTMLResponse)
async def get_settings_partial(request: Request, name: str) -> HTMLResponse:
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
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    config_dir = resolved / "config" / service

    def _read(path: pathlib.Path) -> str | None:
        return path.read_text(encoding="utf-8") if path.exists() else None

    return _get_templates(request).TemplateResponse(
        request,
        "environments/service_config.html",
        {
            "env": env,
            "service": service,
            "config_dir": config_dir,
            "config_content": _read(config_dir / "config.yaml"),
            "logging_content": _read(config_dir / "logging.yaml"),
        },
    )


def _get_log_file(env_root: pathlib.Path, service: str) -> pathlib.Path | None:
    """Return the log file path from the service's logging.yaml, or None."""
    logging_yaml = env_root / "config" / service / "logging.yaml"
    if not logging_yaml.exists():
        return None
    try:
        data = yaml.safe_load(logging_yaml.read_text(encoding="utf-8"))
        filename = data["handlers"]["file"]["filename"]
        path = pathlib.Path(filename)
        return path if path.is_absolute() else env_root / path
    except (KeyError, TypeError, AttributeError):
        return None


@router.get("/{name}/services/{service}/log", response_class=HTMLResponse)
async def service_log(request: Request, name: str, service: str) -> HTMLResponse:
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
async def service_log_stream(request: Request, name: str, service: str) -> StreamingResponse:
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
async def service_log_download(request: Request, name: str, service: str) -> FileResponse:
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


def _check_lock(lock_path: pathlib.Path, timeout: int) -> tuple[bool, str | None, str | None, float | None]:
    """Return (is_locked, token_if_locked, locked_since_str, locked_since_ts).

    Removes stale lock files automatically.
    """
    if not lock_path.exists():
        return False, None, None, None
    try:
        parts = lock_path.read_text(encoding="utf-8").strip().split("\n", 1)
        token = parts[0]
        ts = float(parts[1]) if len(parts) > 1 else 0.0
        if time.time() - ts < timeout:
            locked_since = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            return True, token, locked_since, ts
        lock_path.unlink(missing_ok=True)
    except Exception:
        lock_path.unlink(missing_ok=True)
    return False, None, None, None


@router.post("/{name}/dotenv/force-unlock")
async def force_unlock_dotenv(request: Request, name: str) -> JSONResponse:
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
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    resolved = env.resolved_root_path(cfg.default_environment_base_path)
    lock_path = resolved / "config" / ".env.lock"

    is_locked, _, locked_since, locked_since_ts = _check_lock(lock_path, cfg.file_edit_lock_timeout_sec)
    if is_locked:
        return JSONResponse({"ok": False, "locked_since": locked_since, "locked_since_ts": locked_since_ts}, status_code=409)

    ts = time.time()
    token = str(uuid.uuid4())
    lock_path.write_text(f"{token}\n{ts}", encoding="utf-8")
    return JSONResponse({"ok": True, "token": token, "acquired_ts": ts})


@router.post("/{name}/dotenv/unlock")
async def release_dotenv_lock(request: Request, name: str, body: _UnlockBody) -> JSONResponse:
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
    return JSONResponse({"ok": False, "error": "Lock not held or token mismatch."}, status_code=403)


@router.post("/{name}/dotenv/save")
async def save_dotenv(request: Request, name: str, body: _SaveBody) -> JSONResponse:
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
        backup_ts = datetime.now().strftime("%Y%m%d%H%M%S")
        shutil.copy2(dotenv_path, dotenv_path.parent / f".env.{backup_ts}")

    dotenv_path.write_text(body.content, encoding="utf-8")
    lock_path.unlink(missing_ok=True)
    return JSONResponse({"ok": True})


@router.get("/{name}/dotenv/download")
async def environment_dotenv_download(request: Request, name: str) -> FileResponse:
    cfg = _get_config(request)
    environments = cfg.load_environments()
    env = next((e for e in environments if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    dotenv_path = env.resolved_root_path(cfg.default_environment_base_path) / "config" / ".env"
    if not dotenv_path.exists():
        raise HTTPException(status_code=404, detail="config/.env not found.")
    return FileResponse(path=dotenv_path, filename=".env", media_type="text/plain")


@router.get("/{name}/dotenv", response_class=HTMLResponse)
async def environment_dotenv(request: Request, name: str) -> HTMLResponse:
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

    is_locked, _, locked_since, locked_since_ts = _check_lock(lock_path, cfg.file_edit_lock_timeout_sec)

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
            meta.get("engine_version") and meta.get("tranqu_version") and meta.get("gateway_version")
        )
    return _get_templates(request).TemplateResponse(request, template_name, ctx)


@router.delete("/{name}", response_class=HTMLResponse)
async def delete_environment(request: Request, name: str) -> HTMLResponse:
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
