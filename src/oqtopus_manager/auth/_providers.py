"""Authentication providers implementing the Null Object Pattern."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, override

import jwt
from jwt import PyJWKClient

if TYPE_CHECKING:
    from fastapi import Request

    from ._config import AuthConfig, SignatureVerificationConfig

# One PyJWKClient per issuer URL; kept alive for JWKS key caching across requests
_jwks_clients: dict[str, PyJWKClient] = {}


@dataclass
class AuthUser:
    """Authenticated user extracted from request headers."""

    email: str
    role: str
    raw_groups: list[str] = field(default_factory=list)


class AuthenticationError(Exception):
    """Raised by a provider when the request should be rejected with 403."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AuthProvider(ABC):
    """Abstract base for authentication providers."""

    @abstractmethod
    async def authenticate(self, request: Request) -> AuthUser | None:
        """Authenticate the request.

        Returns:
            ``AuthUser`` on success, or ``None`` when the provider is disabled
            (Null Object — passes the request through without a user).

        Raises:
            AuthenticationError: If the request should be rejected with 403.

        """


class NullAuthProvider(AuthProvider):
    """No-op provider for ``provider: none``; passes every request without a user."""

    @override
    async def authenticate(self, request: Request) -> AuthUser | None:
        """Return ``None`` for every request (authentication is disabled).

        Returns:
            Always ``None``.

        """
        return None


def _verify_jwt(token: str, sig_cfg: SignatureVerificationConfig) -> None:
    """Verify JWT signature and iss/aud claims via the issuer's JWKS endpoint."""
    issuer = sig_cfg.issuer
    if issuer not in _jwks_clients:
        jwks_uri = f"{issuer.rstrip('/')}/.well-known/jwks.json"
        _jwks_clients[issuer] = PyJWKClient(jwks_uri, cache_jwk_set=True, lifespan=300)
    signing_key = _jwks_clients[issuer].get_signing_key_from_jwt(token)
    jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=sig_cfg.audience,
        issuer=issuer,
    )


class HeaderAuthProvider(AuthProvider):
    """Provider that extracts user and role from HTTP headers set by a reverse proxy."""

    def __init__(self, cfg: AuthConfig) -> None:
        self._cfg = cfg

    @override
    async def authenticate(self, request: Request) -> AuthUser | None:
        """Extract user from proxy headers and validate JWT signature if configured.

        Returns:
            Authenticated ``AuthUser``.

        Raises:
            AuthenticationError: If role mapping fails or JWT verification fails.

        """
        cfg = self._cfg
        email = request.headers.get(cfg.user_header, "")
        raw_groups_str = request.headers.get(cfg.roles_header, "")
        raw_groups = [g.strip() for g in raw_groups_str.split(",") if g.strip()]

        role = next(
            (cfg.role_mappings[g] for g in raw_groups if g in cfg.role_mappings),
            None,
        )
        if role is None:
            msg = "no matching role"
            raise AuthenticationError(msg)

        sig = cfg.signature_verification
        if sig and sig.enabled:
            auth_header = request.headers.get(sig.header, "")
            if not auth_header.lower().startswith("bearer "):
                msg = "missing JWT"
                raise AuthenticationError(msg)
            token = auth_header[len("bearer ") :]
            try:
                _verify_jwt(token, sig)
            except Exception:  # noqa: BLE001
                msg = "invalid JWT"
                raise AuthenticationError(msg) from None  # hide internal JWT details

        return AuthUser(email=email, role=role, raw_groups=raw_groups)


def build_provider(cfg: AuthConfig) -> AuthProvider:
    """Instantiate the appropriate provider based on the configuration.

    Returns:
        The configured ``AuthProvider`` instance.

    Raises:
        ValueError: If the provider name is not recognized.

    """
    if cfg.provider == "none":
        return NullAuthProvider()
    if cfg.provider == "header":
        return HeaderAuthProvider(cfg)
    msg = f"Unknown auth provider: {cfg.provider!r}"
    raise ValueError(msg)
