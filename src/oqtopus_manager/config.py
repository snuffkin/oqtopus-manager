"""Application configuration loader."""

import pathlib

import yaml
from oqtopus_util.config import load_config
from pydantic import BaseModel

from oqtopus_manager.auth import (
    AuthConfig,
    HeaderProviderConfig,
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
    host: str = "127.0.0.1"
    port: int = 8000
    log_tail_lines: int = 100
    log_buffer_lines: int = 1000
    app_name: str = "OQTOPUS Manager"
    app_icon_path: pathlib.Path | None = None
    favicon_path: pathlib.Path | None = None
    file_edit_lock_timeout_sec: int = 600
    environment_templates: list[str] = ["backend"]
    sidebar_links: list[SidebarLink] = []
    auth: AuthConfig = AuthConfig()
    enable_debug_endpoint: bool = False

    @classmethod
    def load(cls, config_path: pathlib.Path) -> AppConfig:
        """Load AppConfig from a YAML file.

        Relative paths in the config are resolved against the current working
        directory so that paths behave predictably regardless of where the
        config file itself lives.

        Returns:
            The loaded AppConfig instance.

        """
        raw = load_config(str(config_path))

        cwd = pathlib.Path.cwd()
        server = raw.get("server", {})
        behavior = raw.get("behavior", {})
        appearance = raw.get("appearance", {})
        auth_raw = raw.get("auth", {})
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
        auth = AuthConfig(
            provider=auth_raw.get("provider", "none"),
            header=HeaderProviderConfig(
                jwt_header=header_raw.get("jwt_header", "authorization"),
                user_claim=header_raw.get("user_claim", "email"),
                roles_claim=header_raw.get("roles_claim", "cognito:groups"),
                allow_raw_roles=header_raw.get("allow_raw_roles") or [],
                signature_verification=sig_ver,
                signout_url=header_raw.get("signout_url"),
            ),
            role_mappings=auth_raw.get("role_mappings") or {},
        )

        default_base = cwd / pathlib.Path(server["default_environment_base_path"])
        environments_file = cwd / pathlib.Path(server["environments_file"])

        return cls(
            config_path=config_path.resolve(),
            enable_debug_endpoint=bool(raw.get("enable_debug_endpoint", False)),
            default_environment_base_path=default_base.resolve(),
            environments_file=environments_file.resolve(),
            host=server.get("host", "127.0.0.1"),
            port=server.get("port", 8000),
            log_tail_lines=behavior.get("log_tail_lines", 100),
            log_buffer_lines=behavior.get("log_buffer_lines", 1000),
            app_name=appearance.get("app_name", "OQTOPUS Manager"),
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
            file_edit_lock_timeout_sec=behavior.get("file_edit_lock_timeout_sec", 600),
            environment_templates=appearance.get("environment_templates", ["backend"]),
            sidebar_links=[
                SidebarLink(**item) for item in (appearance.get("sidebar_links") or [])
            ],
            auth=auth,
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
