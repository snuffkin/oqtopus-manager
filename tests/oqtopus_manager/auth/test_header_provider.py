"""Unit tests for auth/header_provider.py."""

from __future__ import annotations

from oqtopus_manager.auth.header_provider import _extract_roles, _get_claim, extract_token


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
