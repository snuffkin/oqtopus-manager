"""Route for the application settings page."""

import asyncio
import shutil

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/settings", tags=["settings"])


async def _run_quick(argv: list[str]) -> str:
    """Run a short-lived command and return its output, or an error string."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        out = stdout.decode(errors="replace").strip()
        return out if out else stderr.decode(errors="replace").strip()
    except FileNotFoundError:
        return "command not found"
    except asyncio.TimeoutError:
        return "timeout"


@router.get("", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    cfg = request.app.state.config

    def _read(path):
        return path.read_text(encoding="utf-8") if path.exists() else f"# File not found: {path}"

    logging_path = cfg.config_path.parent / "logging.yaml"
    oqtopus_path = shutil.which("oqtopus") or "not found"
    raw_version = await _run_quick(["oqtopus", "version"])
    oqtopus_version = raw_version.removeprefix("oqtopus ").strip()

    return request.app.state.templates.TemplateResponse(
        request,
        "app_settings.html",
        {
            "config_path": cfg.config_path,
            "config_content": _read(cfg.config_path),
            "logging_path": logging_path,
            "logging_content": _read(logging_path),
            "oqtopus_path": oqtopus_path,
            "oqtopus_version": oqtopus_version,
        },
    )
