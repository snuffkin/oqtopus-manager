"""Tests for AppConfig loading and environment persistence."""

import pathlib

import pytest
import yaml

from oqtopus_manager.config import AppConfig
from oqtopus_manager.models.environment import Environment


def _write_config(config_dir: pathlib.Path, envs_path: str = "./environments.yaml") -> pathlib.Path:
    """Write a minimal config.yaml and return its path."""
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "server": {
                    "default_environment_base_path": "./environments",
                    "environments_file": envs_path,
                }
            }
        ),
        encoding="utf-8",
    )
    return config_path


def test_load_resolves_relative_paths_from_cwd(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    cfg = AppConfig.load(config_path)
    assert cfg.default_environment_base_path == (tmp_path / "environments").resolve()
    assert cfg.environments_file == (tmp_path / "environments.yaml").resolve()


def test_address_defaults(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    cfg = AppConfig.load(config_path)
    assert cfg.address == "127.0.0.1:8000"
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8000


def test_address_custom(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "server": {
                    "default_environment_base_path": "./environments",
                    "environments_file": "./environments.yaml",
                    "address": "0.0.0.0:9000",
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = AppConfig.load(config_path)
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9000


def test_load_environments_returns_empty_when_file_missing(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    cfg = AppConfig.load(config_path)
    assert cfg.load_environments() == []


def test_save_and_load_environments(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    cfg = AppConfig.load(config_path)

    envs = [
        Environment(name="dev", template="backend"),
        Environment(name="staging", template="backend", root_path=pathlib.Path("./envs/staging")),
    ]
    cfg.save_environments(envs)

    loaded = cfg.load_environments()
    assert len(loaded) == 2
    assert loaded[0].name == "dev"
    assert loaded[0].template == "backend"
    assert loaded[0].root_path is None
    assert loaded[1].name == "staging"
    assert loaded[1].root_path == pathlib.Path("./envs/staging")


def test_save_environments_creates_parent_directory(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path, envs_path="./subdir/environments.yaml")
    cfg = AppConfig.load(config_path)
    cfg.save_environments([Environment(name="dev", template="backend")])
    assert cfg.environments_file.exists()
