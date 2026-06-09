"""Authentication package: providers and configuration models (framework-agnostic)."""

from .config import AuthConfig, HeaderProviderConfig, SignatureVerificationConfig
from .header_provider import HeaderProvider
from .null_provider import NullProvider
from .providers import AuthenticationError, AuthProvider, AuthUser, build_provider

__all__ = [
    "AuthConfig",
    "AuthProvider",
    "AuthUser",
    "AuthenticationError",
    "HeaderProvider",
    "HeaderProviderConfig",
    "NullProvider",
    "SignatureVerificationConfig",
    "build_provider",
]
