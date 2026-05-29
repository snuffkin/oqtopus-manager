"""FastAPI application factory and entry point."""

import argparse
import logging.config
import pathlib

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from oqtopus_manager.config import AppConfig
from oqtopus_manager.routers import app_settings, backend, browse, environments

_TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"


def create_app(config_path: pathlib.Path) -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        The configured FastAPI application instance.

    """
    cfg = AppConfig.load(config_path)

    app = FastAPI(title=cfg.app_name)
    app.state.config = cfg
    templates = Jinja2Templates(directory=_TEMPLATES_DIR)
    templates.env.globals["app_name"] = cfg.app_name
    templates.env.globals["has_app_icon"] = cfg.app_icon_path is not None
    templates.env.globals["has_favicon"] = cfg.favicon_path is not None
    templates.env.globals["sidebar_links"] = cfg.sidebar_links
    app.state.templates = templates

    assets_dir = pathlib.Path.cwd() / "assets"
    assets_dir.mkdir(exist_ok=True)
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    app.include_router(backend.router)
    app.include_router(environments.router)
    app.include_router(browse.router)
    app.include_router(app_settings.router)

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/backend")

    @app.get("/app-icon")
    async def app_icon_file() -> FileResponse:
        icon_path = app.state.config.app_icon_path
        if icon_path and icon_path.exists():
            return FileResponse(path=icon_path)
        raise HTTPException(status_code=404, detail="No app icon configured.")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse:
        fav_path = app.state.config.favicon_path
        if fav_path and fav_path.exists():
            return FileResponse(path=fav_path)
        raise HTTPException(status_code=404, detail="No favicon configured.")

    @app.get("/api-docs", response_class=HTMLResponse)
    async def api_docs_page(request: Request) -> HTMLResponse:
        return app.state.templates.TemplateResponse(request, "api_docs.html", {})

    return app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OQTOPUS Manager")
    parser.add_argument("-c", "--config", default="config/config.yaml")
    parser.add_argument("-l", "--logging", default="config/logging.yaml")
    args, _ = parser.parse_known_args()
    return args


if __name__ == "__main__":
    args = _parse_args()

    with pathlib.Path(args.logging).open(encoding="utf-8") as f:
        logging.config.dictConfig(yaml.safe_load(f))

    cfg_path = pathlib.Path(args.config)
    app = create_app(cfg_path)
    cfg = app.state.config
    uvicorn.run(app, host=cfg.host, port=cfg.port)
