"""Integration tests for backend service_config routes."""

from __future__ import annotations

import pathlib
import time
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient

from oqtopus_manager.main import create_app

_CONFIG = {
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


@pytest.fixture
def tmp_env(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Pre-registered backend 'demo' environment with config files."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(yaml.dump(_CONFIG), encoding="utf-8")
    (tmp_path / "environments.yaml").write_text(
        yaml.dump({"environments": [{"name": "demo", "template": "backend"}]}),
        encoding="utf-8",
    )
    cfg_dir = tmp_path / "environments" / "demo" / "config" / "engine"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.yaml").write_text("key: value\n", encoding="utf-8")
    (cfg_dir / "logging.yaml").write_text("version: 1\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(tmp_env: pathlib.Path) -> TestClient:
    return TestClient(create_app(tmp_env / "config.yaml"), raise_server_exceptions=True)


def _lock_path(tmp_env: pathlib.Path, service: str, which: str) -> pathlib.Path:
    return (
        tmp_env
        / "environments"
        / "demo"
        / "config"
        / service
        / f"{which}.lock"
    )


def _write_lock(lock_path: pathlib.Path) -> str:
    tok = str(uuid.uuid4())
    lock_path.write_text(f"{tok}\n{time.time()}", encoding="utf-8")
    return tok


def _setup_topology(tmp_env: pathlib.Path) -> pathlib.Path:
    """Create gateway config.yaml pointing to a topology JSON file."""
    topo = tmp_env / "environments" / "demo" / "topology.json"
    topo.write_text('{"qubits": 2}', encoding="utf-8")
    gw_cfg_dir = tmp_env / "environments" / "demo" / "config" / "gateway"
    gw_cfg_dir.mkdir(parents=True, exist_ok=True)
    (gw_cfg_dir / "config.yaml").write_text(
        yaml.dump({"device_topology_json_path": str(topo)}),
        encoding="utf-8",
    )
    return topo


# ── service config view ───────────────────────────────────────────────────────


class TestServiceConfigView:
    def test_renders_page(self, client: TestClient) -> None:
        resp = client.get("/backend/demo/services/engine/config")
        assert resp.status_code == 200
        assert b"engine" in resp.content

    def test_nonexistent_env_returns_404(self, client: TestClient) -> None:
        assert client.get("/backend/ghost/services/engine/config").status_code == 404

    def test_renders_when_config_files_missing(
        self, client: TestClient, tmp_env: pathlib.Path
    ) -> None:
        # Delete the config files; page should still render (content=None)
        (tmp_env / "environments" / "demo" / "config" / "engine" / "config.yaml").unlink()
        resp = client.get("/backend/demo/services/engine/config")
        assert resp.status_code == 200


# ── service config lock / unlock / force-unlock ───────────────────────────────


class TestServiceConfigLock:
    def test_acquire_lock_returns_token(self, client: TestClient) -> None:
        resp = client.post("/backend/demo/services/engine/config/config/lock")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "token" in resp.json()

    def test_acquire_already_locked_returns_409(
        self, client: TestClient, tmp_env: pathlib.Path
    ) -> None:
        _write_lock(_lock_path(tmp_env, "engine", "config.yaml"))
        resp = client.post("/backend/demo/services/engine/config/config/lock")
        assert resp.status_code == 409

    def test_unlock_correct_token_succeeds(
        self, client: TestClient, tmp_env: pathlib.Path
    ) -> None:
        lp = _lock_path(tmp_env, "engine", "config.yaml")
        tok = _write_lock(lp)
        resp = client.post(
            "/backend/demo/services/engine/config/config/unlock",
            json={"token": tok},
        )
        assert resp.status_code == 200
        assert not lp.exists()

    def test_unlock_wrong_token_returns_403(
        self, client: TestClient, tmp_env: pathlib.Path
    ) -> None:
        _write_lock(_lock_path(tmp_env, "engine", "config.yaml"))
        resp = client.post(
            "/backend/demo/services/engine/config/config/unlock",
            json={"token": "wrong"},
        )
        assert resp.status_code == 403

    def test_force_unlock_clears_lock(
        self, client: TestClient, tmp_env: pathlib.Path
    ) -> None:
        lp = _lock_path(tmp_env, "engine", "config.yaml")
        _write_lock(lp)
        resp = client.post(
            "/backend/demo/services/engine/config/config/force-unlock"
        )
        assert resp.status_code == 200
        assert not lp.exists()

    def test_invalid_which_returns_400(self, client: TestClient) -> None:
        assert (
            client.post(
                "/backend/demo/services/engine/config/unknown/lock"
            ).status_code
            == 400
        )

    def test_logging_lock_acquire(self, client: TestClient) -> None:
        resp = client.post("/backend/demo/services/engine/config/logging/lock")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ── service config save ────────────────────────────────────────────────────────


class TestServiceConfigSave:
    def test_saves_content(self, client: TestClient, tmp_env: pathlib.Path) -> None:
        tok = client.post(
            "/backend/demo/services/engine/config/config/lock"
        ).json()["token"]
        resp = client.post(
            "/backend/demo/services/engine/config/config/save",
            json={"token": tok, "content": "new: content\n"},
        )
        assert resp.json()["ok"] is True
        cfg = (
            tmp_env / "environments" / "demo" / "config" / "engine" / "config.yaml"
        )
        assert cfg.read_text() == "new: content\n"

    def test_no_lock_returns_409(self, client: TestClient) -> None:
        resp = client.post(
            "/backend/demo/services/engine/config/config/save",
            json={"token": "any", "content": ""},
        )
        assert resp.status_code == 409


# ── topology JSON routes ─────────────────────────────────────────────────────


class TestTopologyRoutes:
    def test_force_unlock_returns_ok(
        self, client: TestClient, tmp_env: pathlib.Path
    ) -> None:
        _setup_topology(tmp_env)
        resp = client.post("/backend/demo/gateway/topology-json/force-unlock")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_force_unlock_no_topology_returns_404(
        self, client: TestClient
    ) -> None:
        # No gateway config.yaml → _resolve_topology_path raises 404
        assert (
            client.post(
                "/backend/demo/gateway/topology-json/force-unlock"
            ).status_code
            == 404
        )

    def test_lock_returns_token(
        self, client: TestClient, tmp_env: pathlib.Path
    ) -> None:
        _setup_topology(tmp_env)
        resp = client.post("/backend/demo/gateway/topology-json/lock")
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_unlock_correct_token(
        self, client: TestClient, tmp_env: pathlib.Path
    ) -> None:
        topo = _setup_topology(tmp_env)
        lp = topo.parent / f"{topo.name}.lock"
        tok = _write_lock(lp)
        resp = client.post(
            "/backend/demo/gateway/topology-json/unlock", json={"token": tok}
        )
        assert resp.status_code == 200
        assert not lp.exists()

    def test_save_writes_content(
        self, client: TestClient, tmp_env: pathlib.Path
    ) -> None:
        topo = _setup_topology(tmp_env)
        tok = client.post("/backend/demo/gateway/topology-json/lock").json()["token"]
        resp = client.post(
            "/backend/demo/gateway/topology-json/save",
            json={"token": tok, "content": '{"qubits": 10}'},
        )
        assert resp.json()["ok"] is True
        assert topo.read_text() == '{"qubits": 10}'

    def test_download_returns_file(
        self, client: TestClient, tmp_env: pathlib.Path
    ) -> None:
        _setup_topology(tmp_env)
        resp = client.get("/backend/demo/gateway/topology-json/download")
        assert resp.status_code == 200
        assert b"qubits" in resp.content

    def test_download_missing_topology_file_returns_404(
        self, client: TestClient, tmp_env: pathlib.Path
    ) -> None:
        topo = _setup_topology(tmp_env)
        topo.unlink()
        assert (
            client.get(
                "/backend/demo/gateway/topology-json/download"
            ).status_code
            == 404
        )

    def test_download_no_topology_configured_returns_404(
        self, client: TestClient
    ) -> None:
        assert (
            client.get(
                "/backend/demo/gateway/topology-json/download"
            ).status_code
            == 404
        )
