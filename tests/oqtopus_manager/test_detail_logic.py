"""Unit tests for pure business-logic functions in backend/detail and cloud_local/detail."""

from __future__ import annotations

import pytest

from oqtopus_manager.routers.backend.detail import _build_args as _be_build_args
from oqtopus_manager.routers.cloud_local.detail import (
    _build_args as _cl_build_args,
    _build_component_args,
    _build_service_args,
    _validate_component,
)


# ── backend._build_args ───────────────────────────────────────────────────────

_DEFAULTS: dict = {
    "service": "all",
    "component": "engine",
    "version": "",
    "foreground": False,
    "status": "",
    "skip_sse_build": False,
}


def _be(cmd: str, **kwargs: object) -> list[str]:
    """Call _be_build_args with defaults overridden by kwargs."""
    params = {**_DEFAULTS, **kwargs}
    return _be_build_args(cmd, **params)  # type: ignore[arg-type]


class TestBackendBuildArgs:
    def test_status(self) -> None:
        assert _be("status") == ["status"]

    def test_info(self) -> None:
        assert _be("info") == ["info"]

    def test_start_valid_service(self) -> None:
        assert _be("start", service="core") == ["start", "core"]

    def test_start_with_foreground(self) -> None:
        assert _be("start", service="all", foreground=True) == [
            "start",
            "all",
            "--foreground",
        ]

    def test_stop_valid_service(self) -> None:
        assert _be("stop", service="gateway") == ["stop", "gateway"]

    def test_restart_valid_service(self) -> None:
        assert _be("restart", service="tranqu") == ["restart", "tranqu"]

    def test_start_invalid_service_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid service"):
            _be("start", service="no-such-service")

    def test_versions_valid_component(self) -> None:
        assert _be("versions", component="engine") == ["versions", "engine"]

    def test_versions_invalid_component_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid component"):
            _be("versions", component="bogus")

    def test_install_all(self) -> None:
        assert _be("install", component="all") == ["install", "all"]

    def test_install_component_with_version(self) -> None:
        assert _be("install", component="engine", version="v1.2") == [
            "install",
            "engine",
            "v1.2",
        ]

    def test_install_skip_sse_build(self) -> None:
        result = _be("install", component="engine", skip_sse_build=True)
        assert "--skip-sse-build" in result

    def test_install_invalid_component_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid component"):
            _be("install", component="unknown")

    def test_update_valid_component(self) -> None:
        assert _be("update", component="tranqu") == ["update", "tranqu"]

    def test_update_invalid_component_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid component"):
            _be("update", component="bogus")

    def test_uninstall_with_version(self) -> None:
        assert _be("uninstall", component="gateway", version="v2.0") == [
            "uninstall",
            "gateway",
            "v2.0",
        ]

    def test_uninstall_missing_version_raises(self) -> None:
        with pytest.raises(ValueError, match="version is required"):
            _be("uninstall", component="gateway", version="")

    def test_uninstall_invalid_component_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid component"):
            _be("uninstall", component="bogus", version="v1")

    def test_build(self) -> None:
        assert _be("build") == ["build", "sse-runtime"]

    def test_device_status_show(self) -> None:
        assert _be("device-status-show") == ["device-status", "show"]

    def test_device_status_set_valid(self) -> None:
        assert _be("device-status-set", status="active") == ["device-status", "active"]

    def test_device_status_set_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid status"):
            _be("device-status-set", status="broken")

    def test_unknown_command_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown command"):
            _be("no-such-cmd")


# ── cloud-local helpers ───────────────────────────────────────────────────────


class TestValidateComponent:
    def test_valid_components_no_error(self) -> None:
        for comp in ("cloud", "frontend", "admin"):
            _validate_component(comp)  # must not raise

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid component"):
            _validate_component("bogus")

    def test_all_disallowed_by_default(self) -> None:
        with pytest.raises(ValueError, match="Invalid component"):
            _validate_component("all")

    def test_all_allowed_with_flag(self) -> None:
        _validate_component("all", allow_all=True)  # must not raise


class TestBuildServiceArgs:
    def test_start_without_foreground(self) -> None:
        assert _build_service_args("start", "all", False) == ["start", "all"]

    def test_start_with_foreground(self) -> None:
        assert _build_service_args("start", "worker", True) == [
            "start",
            "worker",
            "--foreground",
        ]

    def test_stop_foreground_flag_ignored(self) -> None:
        # --foreground is only appended for "start"
        assert _build_service_args("stop", "db", True) == ["stop", "db"]

    def test_invalid_service_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid service"):
            _build_service_args("start", "bogus", False)


class TestBuildComponentArgs:
    def test_versions(self) -> None:
        assert _build_component_args("versions", "cloud", "") == ["versions", "cloud"]

    def test_install_all_no_version(self) -> None:
        assert _build_component_args("install", "all", "") == ["install", "all"]

    def test_install_component_with_version(self) -> None:
        assert _build_component_args("install", "frontend", "v1") == [
            "install",
            "frontend",
            "v1",
        ]

    def test_update(self) -> None:
        assert _build_component_args("update", "admin", "") == ["update", "admin"]

    def test_uninstall_with_version(self) -> None:
        assert _build_component_args("uninstall", "cloud", "v2") == [
            "uninstall",
            "cloud",
            "v2",
        ]

    def test_uninstall_missing_version_raises(self) -> None:
        with pytest.raises(ValueError, match="version is required"):
            _build_component_args("uninstall", "cloud", "")


class TestCloudLocalBuildArgs:
    def test_status(self) -> None:
        assert _cl_build_args("status", "all", "cloud", "", False) == ["status"]

    def test_info(self) -> None:
        assert _cl_build_args("info", "all", "cloud", "", False) == ["info"]

    def test_start_delegates_to_service_args(self) -> None:
        assert _cl_build_args("start", "db", "cloud", "", False) == ["start", "db"]

    def test_versions_delegates_to_component_args(self) -> None:
        assert _cl_build_args("versions", "all", "cloud", "", False) == [
            "versions",
            "cloud",
        ]

    def test_unknown_command_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown command"):
            _cl_build_args("bogus", "all", "cloud", "", False)
