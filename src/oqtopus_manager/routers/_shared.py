"""Shared helper functions for environment router modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

    from oqtopus_manager.config import AppConfig
    from oqtopus_manager.models.environment import Environment


def _get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def _get_config(request: Request) -> AppConfig:
    return request.app.state.config


def _get_environment_or_404(name: str, cfg: AppConfig) -> Environment:
    """Return the named environment, raising 404 if not found.

    Returns:
        The matching Environment.

    Raises:
        HTTPException: If the environment is not found.

    """
    env = next((e for e in cfg.load_environments() if e.name == name), None)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{name}' not found.")
    return env
