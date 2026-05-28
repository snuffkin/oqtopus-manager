"""Application configuration loader."""

import pathlib

import yaml
from pydantic import BaseModel

from oqtopus_manager.models.environment import Environment


class AppConfig(BaseModel):
    """Top-level application configuration."""

    config_path: pathlib.Path
    default_environment_base_path: pathlib.Path
    environments_file: pathlib.Path
    address: str = "127.0.0.1:8000"
    log_tail_lines: int = 100
    log_buffer_lines: int = 1000
    app_name: str = "OQTOPUS Manager"
    app_icon_path: pathlib.Path | None = None
    favicon_path: pathlib.Path | None = None

    @property
    def host(self) -> str:
        """Hostname extracted from *address*."""
        return self.address.rsplit(":", 1)[0]

    @property
    def port(self) -> int:
        """Port number extracted from *address*."""
        return int(self.address.rsplit(":", 1)[1])

    @classmethod
    def load(cls, config_path: pathlib.Path) -> "AppConfig":
        """Load AppConfig from a YAML file.

        Relative paths in the config are resolved against the current working
        directory so that paths behave predictably regardless of where the
        config file itself lives.
        """
        with config_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        cwd = pathlib.Path.cwd()
        default_base = cwd / pathlib.Path(raw["default_environment_base_path"])
        environments_file = cwd / pathlib.Path(raw["environments_file"])

        return cls(
            config_path=config_path.resolve(),
            default_environment_base_path=default_base.resolve(),
            environments_file=environments_file.resolve(),
            address=raw.get("address", "127.0.0.1:8000"),
            log_tail_lines=raw.get("log_tail_lines", 100),
            log_buffer_lines=raw.get("log_buffer_lines", 1000),
            app_name=raw.get("app_name", "OQTOPUS Manager"),
            app_icon_path=(
                (cwd / pathlib.Path(raw["app_icon_path"])).resolve()
                if raw.get("app_icon_path")
                else None
            ),
            favicon_path=(
                (cwd / pathlib.Path(raw["favicon_path"])).resolve()
                if raw.get("favicon_path")
                else None
            ),
        )

    def load_environments(self) -> list[Environment]:
        """Load environments from the environments YAML file.

        Returns an empty list if the file does not exist yet.
        """
        if not self.environments_file.exists():
            return []
        with self.environments_file.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return [Environment(**e) for e in raw.get("environments", [])]

    def save_environments(self, environments: list[Environment]) -> None:
        """Persist environments to the environments YAML file."""
        data = {
            "environments": [
                {k: str(v) if isinstance(v, pathlib.Path) else v for k, v in e.model_dump(exclude_none=True).items()}
                for e in environments
            ]
        }
        self.environments_file.parent.mkdir(parents=True, exist_ok=True)
        with self.environments_file.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
