"""Unit tests for auth/base.py."""

from __future__ import annotations

from oqtopus_manager.auth.base import AuthUser
from oqtopus_manager.auth.providers import AuthenticationError


# ── AuthUser ──────────────────────────────────────────────────────────────────


class TestAuthUser:
    def test_role_returns_first_role(self) -> None:
        user = AuthUser(account="a@b.com", roles=["admin", "user"])
        assert user.role == "admin"

    def test_role_empty_returns_empty_string(self) -> None:
        user = AuthUser(account="a@b.com", roles=[])
        assert user.role == ""


# ── AuthenticationError ───────────────────────────────────────────────────────


class TestAuthenticationError:
    def test_stores_reason(self) -> None:
        err = AuthenticationError("missing JWT")
        assert err.reason == "missing JWT"
        assert str(err) == "missing JWT"
