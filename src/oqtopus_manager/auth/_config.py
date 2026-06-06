"""Pydantic configuration models for authentication."""

from __future__ import annotations

from pydantic import BaseModel


class SignatureVerificationConfig(BaseModel):
    """JWT signature verification sub-config (under provider: header)."""

    enabled: bool = False
    header: str = "authorization"
    issuer: str = ""
    audience: str = ""


class HeaderProviderConfig(BaseModel):
    """Settings specific to the header-based authentication provider."""

    user_header: str = "x-forwarded-email"
    roles_header: str = "x-forwarded-groups"
    signature_verification: SignatureVerificationConfig | None = None
    signout_url: str | None = None


class AuthConfig(BaseModel):
    """Top-level authentication configuration."""

    provider: str = "none"
    header: HeaderProviderConfig = HeaderProviderConfig()
    role_mappings: dict[str, str] = {}
