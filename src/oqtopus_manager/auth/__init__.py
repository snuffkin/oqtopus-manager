"""Authentication package: providers, middleware, and configuration models."""

from ._config import AuthConfig, HeaderProviderConfig, SignatureVerificationConfig
from ._middleware import AuthMiddleware
from ._providers import AuthenticationError, AuthProvider, AuthUser

__all__ = [
    "AuthConfig",
    "AuthMiddleware",
    "AuthProvider",
    "AuthUser",
    "AuthenticationError",
    "HeaderProviderConfig",
    "SignatureVerificationConfig",
]
