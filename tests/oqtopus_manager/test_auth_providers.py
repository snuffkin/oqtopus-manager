"""Unit and integration tests for auth/providers.py."""

from __future__ import annotations

import pathlib

import jwt as pyjwt
import pytest
import yaml
from fastapi.testclient import TestClient

from oqtopus_manager.auth.config import AuthConfig, HeaderProviderConfig, SignatureVerificationConfig
from oqtopus_manager.auth.header_provider import _extract_roles, extract_token, _get_claim
from oqtopus_manager.auth.providers import (
    AuthenticationError,
    AuthUser,
    NullProvider,
    build_provider,
)
from oqtopus_manager.main import create_app
from oqtopus_manager.routers.debug import _decode_jwt_without_verification


# ── AuthUser ──────────────────────────────────────────────────────────────────


class TestAuthUser:
    def test_role_returns_first_role(self) -> None:
        user = AuthUser(email="a@b.com", roles=["admin", "user"])
        assert user.role == "admin"

    def test_role_empty_returns_empty_string(self) -> None:
        user = AuthUser(email="a@b.com", roles=[])
        assert user.role == ""


# ── AuthenticationError ───────────────────────────────────────────────────────


class TestAuthenticationError:
    def test_stores_reason(self) -> None:
        err = AuthenticationError("missing JWT")
        assert err.reason == "missing JWT"
        assert str(err) == "missing JWT"


# ── extract_token ────────────────────────────────────────────────────────────


class TestExtractToken:
    def test_authorization_bearer_stripped(self) -> None:
        assert extract_token("authorization", "Bearer abc.def.ghi") == "abc.def.ghi"

    def test_authorization_bearer_case_insensitive(self) -> None:
        assert extract_token("authorization", "BEARER abc.def.ghi") == "abc.def.ghi"

    def test_authorization_missing_bearer_returns_none(self) -> None:
        assert extract_token("authorization", "abc.def.ghi") is None

    def test_empty_header_returns_none(self) -> None:
        assert extract_token("authorization", "") is None

    def test_custom_header_returns_value_as_is(self) -> None:
        assert extract_token("x-jwt-token", "abc.def.ghi") == "abc.def.ghi"

    def test_custom_header_empty_returns_none(self) -> None:
        assert extract_token("x-jwt-token", "") is None


# ── _get_claim ────────────────────────────────────────────────────────────────


class TestGetClaim:
    def test_string_key_present(self) -> None:
        assert _get_claim({"email": "a@b.com"}, "email") == "a@b.com"

    def test_string_key_missing_returns_none(self) -> None:
        assert _get_claim({}, "email") is None

    def test_nested_list_path(self) -> None:
        payload = {"custom": {"cognito:groups": ["admin"]}}
        assert _get_claim(payload, ["custom", "cognito:groups"]) == ["admin"]

    def test_nested_intermediate_not_dict_returns_none(self) -> None:
        assert _get_claim({"a": "not-a-dict"}, ["a", "b"]) is None

    def test_nested_missing_key_returns_none(self) -> None:
        assert _get_claim({"a": {}}, ["a", "b"]) is None


# ── _extract_roles ────────────────────────────────────────────────────────────


class TestExtractRoles:
    def test_none_returns_empty(self) -> None:
        assert _extract_roles(None) == []

    def test_list_input(self) -> None:
        assert _extract_roles(["admin", "user"]) == ["admin", "user"]

    def test_list_filters_empty_strings(self) -> None:
        assert _extract_roles(["admin", "", "user"]) == ["admin", "user"]

    def test_comma_separated_string(self) -> None:
        assert _extract_roles("admin,user, guest") == ["admin", "user", "guest"]

    def test_other_type_returns_empty(self) -> None:
        assert _extract_roles(42) == []


# ── build_provider ────────────────────────────────────────────────────────────


class TestBuildProvider:
    def _make_auth_cfg(self, provider: str) -> AuthConfig:
        if provider == "header":
            return AuthConfig(
                provider="header",
                header=HeaderProviderConfig(
                    jwt_header="authorization",
                    user_claim="email",
                    roles_claim="groups",
                    allow_raw_roles=[],
                    signature_verification=SignatureVerificationConfig(
                        enabled=False, issuer="https://example.com", audience="aud"
                    ),
                ),
            )
        return AuthConfig(provider=provider)

    def test_none_returns_null_provider(self) -> None:
        cfg = self._make_auth_cfg("none")
        assert isinstance(build_provider(cfg), NullProvider)

    def test_unknown_provider_raises(self) -> None:
        cfg = AuthConfig(provider="unknown")
        with pytest.raises(ValueError, match="Unknown auth provider"):
            build_provider(cfg)


# ── HeaderProvider via HTTP middleware ────────────────────────────────────


_HEADER_AUTH_CONFIG = {
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
    "auth": {
        "provider": "header",
        "header": {
            "jwt_header": "authorization",
            "user_claim": "email",
            "roles_claim": "groups",
            "allow_raw_roles": ["test.*"],
            "signature_verification": {
                "enabled": False,
                "issuer": "https://example.com",
                "audience": "test-audience",
            },
        },
    },
    "enable_debug_endpoint": False,
}


@pytest.fixture
def header_auth_client(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.chdir(tmp_path)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(_HEADER_AUTH_CONFIG), encoding="utf-8")
    (tmp_path / "environments.yaml").write_text("environments: []\n", encoding="utf-8")
    app = create_app(cfg_path)
    return TestClient(app, raise_server_exceptions=False)


def _make_jwt(claims: dict) -> str:
    """Create an unsigned-verifiable HS256 JWT (signature verification disabled in tests)."""
    return pyjwt.encode(claims, "test-secret", algorithm="HS256")


# ── _decode_jwt_without_verification ─────────────────────────────────────────


class TestDecodeJwtWithoutVerification:
    def test_valid_jwt_returns_header_and_payload(self) -> None:
        token = _make_jwt({"email": "u@example.com", "sub": "123"})
        result = _decode_jwt_without_verification(token)
        assert "header" in result
        assert "payload" in result
        assert result["payload"]["email"] == "u@example.com"

    def test_not_enough_parts_returns_error_dict(self) -> None:
        result = _decode_jwt_without_verification("only-one-part")
        assert result == {"error": "Invalid JWT format"}

    def test_two_part_token_returns_header_and_payload(self) -> None:
        # Manually construct a two-part base64url JWT
        import base64, json as _json
        def _b64(d: dict) -> str:
            return base64.urlsafe_b64encode(_json.dumps(d).encode()).rstrip(b"=").decode()
        token = f"{_b64({'alg':'HS256'})}.{_b64({'sub':'abc'})}"
        result = _decode_jwt_without_verification(token)
        assert result["payload"]["sub"] == "abc"


# ── HeaderProvider via HTTP middleware ────────────────────────────────────


class TestHeaderProviderViaMiddleware:
    def test_missing_jwt_returns_403(self, header_auth_client: TestClient) -> None:
        resp = header_auth_client.get("/backend")
        assert resp.status_code == 403

    def test_malformed_bearer_returns_403(self, header_auth_client: TestClient) -> None:
        resp = header_auth_client.get(
            "/backend", headers={"Authorization": "not-bearer-format"}
        )
        assert resp.status_code == 403

    def test_valid_jwt_with_allowed_role_passes(
        self, header_auth_client: TestClient
    ) -> None:
        token = _make_jwt({"email": "u@example.com", "groups": ["test.admin"]})
        resp = header_auth_client.get(
            "/backend", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200

    def test_jwt_with_no_matching_role_returns_403(
        self, header_auth_client: TestClient
    ) -> None:
        token = _make_jwt({"email": "u@example.com", "groups": ["other.role"]})
        resp = header_auth_client.get(
            "/backend", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403

    def test_jwt_with_empty_groups_returns_403(
        self, header_auth_client: TestClient
    ) -> None:
        token = _make_jwt({"email": "u@example.com", "groups": []})
        resp = header_auth_client.get(
            "/backend", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403


# ── /debug endpoint with HeaderProvider ───────────────────────────────────

_HEADER_DEBUG_CONFIG = {
    **_HEADER_AUTH_CONFIG,
    "enable_debug_endpoint": True,
}


@pytest.fixture
def header_debug_client(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """Client with HeaderProvider + debug endpoint enabled."""
    monkeypatch.chdir(tmp_path)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(_HEADER_DEBUG_CONFIG), encoding="utf-8")
    (tmp_path / "environments.yaml").write_text("environments: []\n", encoding="utf-8")
    app = create_app(cfg_path)
    return TestClient(app, raise_server_exceptions=False)


class TestDebugPageWithHeaderAuth:
    def test_debug_shows_decoded_jwt(
        self, header_debug_client: TestClient
    ) -> None:
        # Sending a valid JWT: covers the `if token:` branch in debug_page (lines 54-58)
        token = _make_jwt({"email": "u@example.com", "groups": ["test.admin"]})
        resp = header_debug_client.get(
            "/debug", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200

    def test_debug_allowed_raw_roles_computed(
        self, header_debug_client: TestClient
    ) -> None:
        # valid JWT + user set → covers line 65 (if user and allow_patterns)
        token = _make_jwt({"email": "u@example.com", "groups": ["test.admin", "other.role"]})
        resp = header_debug_client.get(
            "/debug", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
