"""Pydantic configuration models for authentication."""

from __future__ import annotations

from pydantic import BaseModel


class SignatureVerificationConfig(BaseModel):
    """JWT signature verification sub-config (under provider: header)."""

    enabled: bool = False
    header: str = "authorization"
    issuer: str = ""
    audience: str = ""


class AuthConfig(BaseModel):
    """Top-level authentication configuration."""

    provider: str = "none"
    user_header: str = "x-forwarded-email"
    roles_header: str = "x-forwarded-groups"
    signature_verification: SignatureVerificationConfig | None = None
    role_mappings: dict[str, str] = {}
