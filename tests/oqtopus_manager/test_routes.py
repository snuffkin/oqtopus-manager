"""Integration tests for environment routes."""

import pathlib

import pytest
import yaml
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from oqtopus_manager.main import create_app


@pytest.fixture
def config_path(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Write a minimal config.yaml, set CWD to tmp_path, and return config path."""
    monkeypatch.chdir(tmp_path)
    config = {
        "server": {
            "host": "127.0.0.1",
            "port": 8000,
            "default_environment_base_path": "./environments",
            "environments_file": "./environments.yaml",
        },
        "behavior": {
            "log_tail_lines": 100,
            "log_buffer_lines": 1000,
            "file_edit_lock_timeout_sec": 600,
        },
        "appearance": {
            "app_name": "OQTOPUS Manager",
            "environment_templates": ["backend"],
        },
        "enable_debug_endpoint": False,
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(config), encoding="utf-8")
    (tmp_path / "environments.yaml").write_text("environments: []\n", encoding="utf-8")
    return cfg_path


@pytest.fixture
def client(config_path: pathlib.Path) -> TestClient:
    app = create_app(config_path)
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def mock_stream_success(mocker: MockerFixture) -> None:
    """Mock oqtopus init stream to succeed without running the real command."""
    async def _gen(*args, **kwargs):
        yield "data: Initializing...\n\n"
        yield "event: done\ndata: success\n\n"

    mocker.patch("oqtopus_manager.routers.backend.list.stream_oqtopus_init", side_effect=_gen)


@pytest.fixture
def mock_stream_failure(mocker: MockerFixture) -> None:
    """Mock oqtopus init stream to fail."""
    async def _gen(*args, **kwargs):
        yield "data: Error: template not found\n\n"
        yield "event: done\ndata: error\n\n"

    mocker.patch("oqtopus_manager.routers.backend.list.stream_oqtopus_init", side_effect=_gen)


def test_root_redirects_to_backend(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/backend"


def test_list_environments_empty(client: TestClient) -> None:
    response = client.get("/backend")
    assert response.status_code == 200


def test_create_environment_returns_ok(client: TestClient) -> None:
    response = client.post("/backend", data={"name": "demo", "template": "backend", "root_path": ""})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_create_environment_invalid_name_returns_422(client: TestClient) -> None:
    response = client.post("/backend", data={"name": "MyEnv", "template": "backend", "root_path": ""})
    assert response.status_code == 422
    assert response.json()["ok"] is False
    assert "error" in response.json()


def test_create_duplicate_environment_returns_409(client: TestClient, mock_stream_success: None) -> None:
    client.get("/backend/stream?name=demo&template=backend")
    response = client.post("/backend", data={"name": "demo", "template": "backend", "root_path": ""})
    assert response.status_code == 409
    assert response.json()["ok"] is False
    assert "already exists" in response.json()["error"]


def test_stream_success_saves_environment(client: TestClient, mock_stream_success: None) -> None:
    response = client.get("/backend/stream?name=demo&template=backend")
    assert response.status_code == 200
    assert b"event: done" in response.content
    assert b"success" in response.content
    list_response = client.get("/backend")
    assert b"demo" in list_response.content


def test_stream_failure_does_not_save_environment(client: TestClient, mock_stream_failure: None) -> None:
    client.get("/backend/stream?name=demo&template=backend")
    list_response = client.get("/backend")
    assert b"demo" not in list_response.content


def test_get_environment_detail(client: TestClient, mock_stream_success: None) -> None:
    client.get("/backend/stream?name=demo&template=backend")
    response = client.get("/backend/demo")
    assert response.status_code == 200
    assert b"demo" in response.content


def test_get_nonexistent_environment_returns_404(client: TestClient) -> None:
    response = client.get("/backend/nonexistent")
    assert response.status_code == 404


def test_delete_environment(
    client: TestClient, mock_stream_success: None, tmp_path: pathlib.Path
) -> None:
    client.get("/backend/stream?name=myenv&template=backend")
    env_dir = tmp_path / "environments" / "myenv"
    env_dir.mkdir(parents=True, exist_ok=True)
    response = client.request("DELETE", "/backend/myenv")
    assert response.status_code == 200
    assert b"myenv" not in response.content
    assert not env_dir.exists()


def test_delete_environment_without_directory(
    client: TestClient, mock_stream_success: None
) -> None:
    """Delete should succeed even if the directory is already gone."""
    client.get("/backend/stream?name=myenv&template=backend")
    response = client.request("DELETE", "/backend/myenv")
    assert response.status_code == 200


def test_delete_nonexistent_environment_returns_404(client: TestClient) -> None:
    response = client.request("DELETE", "/backend/nonexistent")
    assert response.status_code == 404


def test_new_environment_form(client: TestClient) -> None:
    response = client.get("/backend/new")
    assert response.status_code == 200
