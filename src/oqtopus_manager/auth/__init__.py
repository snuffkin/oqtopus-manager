"""Authentication package: providers, middleware, and configuration models."""

from .config import AuthConfig, HeaderProviderConfig, SignatureVerificationConfig
from .middleware import AuthMiddleware
from .providers import AuthenticationError, AuthProvider, AuthUser, build_provider

__all__ = [
    "AuthConfig",
    "AuthMiddleware",
    "AuthProvider",
    "AuthUser",
    "AuthenticationError",
    "HeaderProviderConfig",
    "SignatureVerificationConfig",
    "build_provider",
]
