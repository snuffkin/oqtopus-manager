"""Pydantic configuration models for authentication."""

from __future__ import annotations

from pydantic import BaseModel


class SignatureVerificationConfig(BaseModel):
    """JWT signature verification sub-config (under provider: header)."""

    enabled: bool = False
    issuer: str = ""  # required when enabled=true; also used to derive jwks_url
    jwks_url: str | None = None  # explicit JWKS endpoint; overrides issuer-derived URL
    audience: str = ""  # required when enabled=true


class HeaderProviderConfig(BaseModel):
    """Settings specific to the header-based authentication provider."""

    # "authorization" → strip "Bearer " prefix automatically
    jwt_header: str
    user_claim: str
    # str = simple key; list[str] = nested path (e.g. ["custom", "cognito:groups"])
    roles_claim: str | list[str] = "cognito:groups"
    # glob patterns on raw roles_claim values, applied before role_mappings
    allow_raw_roles: list[str] = []  # empty = allow all
    signature_verification: SignatureVerificationConfig | None = None
    signout_url: str | None = None


class NoneProviderConfig(BaseModel):
    """Settings for the provider: none (disabled auth) mode."""

    default_account: str
    default_roles: list[str]


class AuthConfig(BaseModel):
    """Top-level authentication configuration."""

    provider: str = "none"
    none: NoneProviderConfig | None = None  # required when provider == "none"
    header: HeaderProviderConfig | None = None  # required when provider == "header"
    role_mappings: dict[str, str] = {}
