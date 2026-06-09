"""Authentication package: providers and configuration models (framework-agnostic)."""

from .config import AuthConfig, HeaderProviderConfig, SignatureVerificationConfig
from .providers import AuthenticationError, AuthProvider, AuthUser, build_provider

__all__ = [
    "AuthConfig",
    "AuthProvider",
    "AuthUser",
    "AuthenticationError",
    "HeaderProviderConfig",
    "SignatureVerificationConfig",
    "build_provider",
]
