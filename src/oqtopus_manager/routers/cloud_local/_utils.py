"""Cloud-local-specific shared helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib

    from oqtopus_manager.config import AppConfig
    from oqtopus_manager.models.environment import Environment

_VERSION_KEYS = ["cloud_version", "frontend_version", "admin_version"]


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
            # Strip prefix so keys match cloud_version/frontend_version/admin_version
            result[key.strip().removeprefix("cloud_local_")] = value.strip()
    return result


def _build_list_context(environments: list[Environment], cfg: AppConfig) -> dict:
    """Build template context for the cloud-local list page.

    Returns:
        Dict with env_items and metadata for the list template.

    """
    env_items = []
    for env in environments:
        resolved = env.resolved_root_path(cfg.default_environment_base_path)
        meta = _read_metadata(resolved)
        all_installed = bool(
            meta.get("cloud_version")
            and meta.get("frontend_version")
            and meta.get("admin_version")
        )
        env_items.append({"env": env, "all_installed": all_installed})
    return {
        "env_items": env_items,
        "base_path": cfg.default_environment_base_path,
        "url_prefix": "/cloud-local",
        "page_title": "Cloud Local",
        "page_description": "Manage your OQTOPUS cloud-local environments.",
        "has_device_status": False,
    }


def _get_log_file(env_root: pathlib.Path, service: str) -> pathlib.Path:
    """Return the log file path for a cloud-local service.

    Returns:
        Path to logs/<service>/service.log under env_root.

    """
    return env_root / "logs" / service / "service.log"
