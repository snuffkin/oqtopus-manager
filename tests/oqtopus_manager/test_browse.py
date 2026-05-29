"""Tests for the directory browser route."""

import pathlib

import pytest
import yaml
from fastapi.testclient import TestClient

from oqtopus_manager.main import create_app


@pytest.fixture
def client(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    config = {
        "server": {
            "default_environment_base_path": "./environments",
            "environments_file": "./environments.yaml",
        }
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(config), encoding="utf-8")
    (tmp_path / "environments.yaml").write_text("environments: []\n", encoding="utf-8")
    app = create_app(cfg_path)
    return TestClient(app)


def test_browse_default_returns_200(client: TestClient) -> None:
    response = client.get("/browse")
    assert response.status_code == 200


def test_browse_shows_subdirectories(client: TestClient, tmp_path: pathlib.Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    response = client.get(f"/browse?path={tmp_path}")
    assert response.status_code == 200
    assert b"alpha" in response.content
    assert b"beta" in response.content


def test_browse_hides_dotfiles(client: TestClient, tmp_path: pathlib.Path) -> None:
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible").mkdir()
    response = client.get(f"/browse?path={tmp_path}")
    assert b".hidden" not in response.content
    assert b"visible" in response.content


def test_browse_invalid_path_falls_back_to_cwd(client: TestClient) -> None:
    response = client.get("/browse?path=/nonexistent/path/xyz")
    assert response.status_code == 200


def test_browse_shows_parent_navigation(client: TestClient, tmp_path: pathlib.Path) -> None:
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    response = client.get(f"/browse?path={subdir}")
    assert response.status_code == 200
    assert b".." in response.content
