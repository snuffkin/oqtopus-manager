"""Unit tests for auth/fastapi/depends.py — require_roles and require_permission."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from oqtopus_manager.auth.config import AuthConfig, NoneProviderConfig
from oqtopus_manager.auth.fastapi import (
    AuthMiddleware,
    FastAPIRoles,
    require_permission,
    require_roles,
)


# ── require_roles / FastAPIRoles ──────────────────────────────────────────────


def _make_roles_test_app(required_roles: tuple[str, ...]) -> FastAPI:
    """Minimal app with a None provider and test routes using require_roles.

    NullProvider grants only the "operator" role.
    """
    auth_cfg = AuthConfig(
        provider="none",
        none=NoneProviderConfig(default_account="test_user", default_roles=["operator"]),
    )
    app = FastAPI()
    app.add_middleware(AuthMiddleware, auth_cfg=auth_cfg)

    roles = FastAPIRoles()

    @app.get("/require-roles-standalone", dependencies=[require_roles(*required_roles)])
    def protected_standalone() -> dict:
        return {"ok": True}

    @app.get("/require-roles-class", dependencies=[roles.require(*required_roles)])
    def protected_class() -> dict:
        return {"ok": True}

    return app


class TestRequireRoles:
    def test_single_matching_role_passes_standalone(self) -> None:
        # NullProvider gives "operator"; require_roles("operator") should pass
        app = _make_roles_test_app(("operator",))
        client = TestClient(app, raise_server_exceptions=True)
        assert client.get("/require-roles-standalone").status_code == 200

    def test_single_matching_role_passes_class(self) -> None:
        app = _make_roles_test_app(("operator",))
        client = TestClient(app, raise_server_exceptions=True)
        assert client.get("/require-roles-class").status_code == 200

    def test_single_non_matching_role_returns_403_standalone(self) -> None:
        # NullProvider gives "operator"; require_roles("admin") should fail
        app = _make_roles_test_app(("admin",))
        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/require-roles-standalone").status_code == 403

    def test_single_non_matching_role_returns_403_class(self) -> None:
        app = _make_roles_test_app(("admin",))
        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/require-roles-class").status_code == 403

    def test_multiple_roles_passes_when_user_holds_one(self) -> None:
        # user has "operator"; require_roles("admin", "operator") → OR logic → pass
        app = _make_roles_test_app(("admin", "operator"))
        client = TestClient(app, raise_server_exceptions=True)
        assert client.get("/require-roles-standalone").status_code == 200

    def test_multiple_roles_returns_403_when_user_holds_none(self) -> None:
        # user has "operator"; require_roles("admin", "superuser") → none match → 403
        app = _make_roles_test_app(("admin", "superuser"))
        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/require-roles-standalone").status_code == 403


# ── require_permission without permissions configured ─────────────────────────


def _make_no_permissions_app() -> FastAPI:
    """Minimal app with no app.state.permissions and a route using require_permission."""
    auth_cfg = AuthConfig(
        provider="none",
        none=NoneProviderConfig(default_account="test_user", default_roles=["operator"]),
    )
    app = FastAPI()
    app.add_middleware(AuthMiddleware, auth_cfg=auth_cfg)
    # app.state.permissions intentionally not set

    @app.get("/protected", dependencies=[require_permission("environment.get")])
    def protected() -> dict:
        return {"ok": True}

    return app


class TestRequirePermissionNotConfigured:
    def test_raises_runtime_error_as_500(self) -> None:
        # RuntimeError from require_permission → FastAPI returns 500
        app = _make_no_permissions_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/protected")
        assert resp.status_code == 500
