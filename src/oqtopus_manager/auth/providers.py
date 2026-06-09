"""Authentication provider factory.

New code should import directly from the sub-modules.
These re-exports keep existing import paths working without modification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from oqtopus_manager.auth.base import AuthenticationError, AuthProvider, AuthUser
from oqtopus_manager.auth.header_provider import HeaderProvider
from oqtopus_manager.auth.null_provider import NullProvider

if TYPE_CHECKING:
    from oqtopus_manager.auth.config import AuthConfig

__all__ = [
    "AuthProvider",
    "AuthUser",
    "AuthenticationError",
    "HeaderProvider",
    "NullProvider",
    "build_provider",
]


def build_provider(cfg: AuthConfig) -> AuthProvider:
    """Instantiate the appropriate provider based on the configuration.

    Returns:
        The configured ``AuthProvider`` instance.

    Raises:
        ValueError: If the provider name is not recognized.

    """
    if cfg.provider == "none":
        return NullProvider()
    if cfg.provider == "header":
        return HeaderProvider(cfg)
    msg = f"Unknown auth provider: {cfg.provider!r}"
    raise ValueError(msg)
