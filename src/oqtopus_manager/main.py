"""FastAPI application factory and entry point."""

import argparse
import importlib.metadata
import pathlib

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from oqtopus_util.config import load_config, setup_logging

from oqtopus_manager.auth import AuthMiddleware
from oqtopus_manager.config import AppConfig
from oqtopus_manager.routers import (
    app_settings,
    backend,
    backend_environments,
    browse,
    cloud_local,
    cloud_local_environments,
    debug,
    me,
)

# Jinja2 templates directory bundled with the package
_TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"

# Maps each template type to its pair of routers (SSE + CRUD)
_TEMPLATE_ROUTERS = {
    "backend": [backend.router, backend_environments.router],
    "cloud-local": [cloud_local.router, cloud_local_environments.router],
}


def create_app(config_path: pathlib.Path) -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        The configured FastAPI application instance.

    Raises:
        ValueError: If no environment_templates are defined in config.

    """
    cfg = AppConfig.load(config_path)

    if not cfg.environment_templates:
        msg = "No environment_templates defined in config."
        raise ValueError(msg)

    # Initialize FastAPI and attach config/templates to app state
    app = FastAPI(
        title=cfg.app_name,
        version=importlib.metadata.version("oqtopus-manager"),
    )
    app.add_middleware(AuthMiddleware, auth_cfg=cfg.auth)
    app.state.config = cfg
    templates = Jinja2Templates(directory=_TEMPLATES_DIR)
    templates.env.globals["app_name"] = cfg.app_name
    templates.env.globals["has_app_icon"] = cfg.app_icon_path is not None
    templates.env.globals["has_favicon"] = cfg.favicon_path is not None
    templates.env.globals["environment_templates"] = cfg.environment_templates
    templates.env.globals["sidebar_links"] = cfg.sidebar_links
    app.state.templates = templates

    # Serve operator-supplied assets (icons, images) from the runtime working directory
    assets_dir = pathlib.Path.cwd() / "assets"
    assets_dir.mkdir(exist_ok=True)
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # Register only the routers for enabled template types
    for tmpl in cfg.environment_templates:
        for router in _TEMPLATE_ROUTERS.get(tmpl, []):
            app.include_router(router)
    app.include_router(browse.router)
    app.include_router(app_settings.router)
    if cfg.auth.provider != "none":
        app.include_router(me.router)
    if cfg.debug:
        app.include_router(debug.router)

    # Redirect / to the first configured template
    default_url = "/" + cfg.environment_templates[0]
    _register_routes(app, default_url)

    return app


def _register_routes(app: FastAPI, default_url: str) -> None:
    """Register app-level routes (redirect, version, assets, docs)."""

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse(url=default_url)

    @app.get("/version")
    async def version() -> dict[str, str]:
        return {"version": app.version}

    # Serve app icon and favicon from operator-configured paths
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OQTOPUS Manager")
    parser.add_argument("-c", "--config", default="config/config.yaml")
    parser.add_argument("-l", "--logging", default="config/logging.yaml")
    args, _ = parser.parse_known_args()
    return args


if __name__ == "__main__":
    args = _parse_args()

    # Load logging config first so all subsequent output is properly formatted
    log_config_dict = load_config(args.logging)
    setup_logging(log_config_dict)

    cfg_path = pathlib.Path(args.config)
    app = create_app(cfg_path)
    cfg = app.state.config
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_config=log_config_dict)
