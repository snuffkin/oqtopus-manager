"""Application configuration loader."""

import pathlib

import yaml
from oqtopus_util.config import load_config
from pydantic import BaseModel

from oqtopus_manager.auth import (
    AuthConfig,
    HeaderProviderConfig,
    NoneProviderConfig,
    SignatureVerificationConfig,
)
from oqtopus_manager.models.environment import Environment


class SidebarLink(BaseModel):
    """A single external link shown in the sidebar LINKS section."""

    label: str
    url: str


class AppConfig(BaseModel):
    """Top-level application configuration."""

    config_path: pathlib.Path
    default_environment_base_path: pathlib.Path
    environments_file: pathlib.Path
    host: str
    port: int
    log_tail_lines: int
    log_buffer_lines: int
    app_name: str
    app_icon_path: pathlib.Path | None
    favicon_path: pathlib.Path | None
    file_edit_lock_timeout_sec: int
    environment_templates: list[str]
    sidebar_links: list[SidebarLink] = []
    auth: AuthConfig = AuthConfig()
    enable_debug_endpoint: bool
    role_permissions: dict[str, frozenset[str]]

    @staticmethod
    def _parse_permissions(raw: dict) -> dict[str, frozenset[str]]:
        """Resolve permissions config including single-level _extends_ inheritance.

        Returns:
            Mapping of role name to resolved frozenset of permissions.

        """
        extends: dict[str, str] = raw.get("_extends_") or {}
        base: dict[str, set[str]] = {
            key: set(value)
            for key, value in raw.items()
            if key != "_extends_" and isinstance(value, list)
        }
        resolved: dict[str, frozenset[str]] = {}
        for role, perms in base.items():
            parent = extends.get(role)
            parent_perms = base.get(parent, set()) if parent else set()
            resolved[role] = frozenset(perms | parent_perms)
        return resolved

    @staticmethod
    def _parse_none_cfg(raw: dict) -> NoneProviderConfig:
        for key in ("default_account", "default_roles"):
            if raw.get(key) is None:
                msg = f"auth.none.{key} is required when provider=none"
                raise ValueError(msg)
        return NoneProviderConfig(
            default_account=raw["default_account"],
            default_roles=raw["default_roles"],
        )

    @classmethod
    def load(cls, config_path: pathlib.Path) -> AppConfig:
        """Load AppConfig from a YAML file.

        Relative paths in the config are resolved against the current working
        directory so that paths behave predictably regardless of where the
        config file itself lives.

        Returns:
            The loaded AppConfig instance.

        Raises:
            ValueError: If required configuration fields are missing or invalid.

        """
        raw = load_config(str(config_path))

        cwd = pathlib.Path.cwd()
        server = raw.get("server", {})
        behavior = raw.get("behavior", {})
        appearance = raw.get("appearance", {})
        auth_raw = raw.get("auth", {})
        provider = auth_raw.get("provider", "none")
        header_cfg: HeaderProviderConfig | None = None
        if provider == "header":
            header_raw = auth_raw.get("header") or {}
            sig_ver_raw = header_raw.get("signature_verification") or {}
            sig_ver = (
                SignatureVerificationConfig(
                    enabled=bool(sig_ver_raw.get("enabled", False)),
                    issuer=sig_ver_raw.get("issuer", ""),
                    jwks_url=sig_ver_raw.get("jwks_url"),
                    audience=sig_ver_raw.get("audience", ""),
                )
                if sig_ver_raw
                else None
            )
            for key in ("jwt_header", "user_claim"):
                if not header_raw.get(key):
                    msg = f"auth.header.{key} is required when provider=header"
                    raise ValueError(msg)
            header_cfg = HeaderProviderConfig(
                jwt_header=header_raw["jwt_header"],
                user_claim=header_raw["user_claim"],
                roles_claim=header_raw.get("roles_claim", "cognito:groups"),
                allow_raw_roles=header_raw.get("allow_raw_roles") or [],
                signature_verification=sig_ver,
                signout_url=header_raw.get("signout_url"),
            )
        auth = AuthConfig(
            provider=provider,
            none=(
                cls._parse_none_cfg(auth_raw.get("none") or {})
                if provider == "none"
                else None
            ),
            header=header_cfg,
            role_mappings=auth_raw.get("role_mappings") or {},
        )
        default_base = cwd / pathlib.Path(server["default_environment_base_path"])
        environments_file = cwd / pathlib.Path(server["environments_file"])

        return cls(
            config_path=config_path.resolve(),
            enable_debug_endpoint=bool(raw["enable_debug_endpoint"]),
            default_environment_base_path=default_base.resolve(),
            environments_file=environments_file.resolve(),
            host=server["host"],
            port=server["port"],
            log_tail_lines=behavior["log_tail_lines"],
            log_buffer_lines=behavior["log_buffer_lines"],
            app_name=appearance["app_name"],
            app_icon_path=(
                (cwd / pathlib.Path(appearance["app_icon_path"])).resolve()
                if appearance.get("app_icon_path")
                else None
            ),
            favicon_path=(
                (cwd / pathlib.Path(appearance["favicon_path"])).resolve()
                if appearance.get("favicon_path")
                else None
            ),
            file_edit_lock_timeout_sec=behavior["file_edit_lock_timeout_sec"],
            environment_templates=appearance["environment_templates"],
            sidebar_links=[
                SidebarLink(**item) for item in (appearance.get("sidebar_links") or [])
            ],
            auth=auth,
            role_permissions=cls._parse_permissions(raw["permissions"]),
        )

    def load_environments(self) -> list[Environment]:
        """Load environments from the environments YAML file.

        Returns an empty list if the file does not exist yet.

        Returns:
            List of Environment instances loaded from the YAML file.

        """
        if not self.environments_file.exists():
            return []
        raw = load_config(str(self.environments_file)) or {}
        return [Environment(**e) for e in raw.get("environments", [])]

    def save_environments(self, environments: list[Environment]) -> None:
        """Persist environments to the environments YAML file."""
        data = {
            "environments": [
                {
                    k: str(v) if isinstance(v, pathlib.Path) else v
                    for k, v in e.model_dump(exclude_none=True).items()
                }
                for e in environments
            ]
        }
        self.environments_file.parent.mkdir(parents=True, exist_ok=True)
        with self.environments_file.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
