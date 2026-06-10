"""Authentication package: providers and configuration models (framework-agnostic)."""

from .config import (
    AuthConfig,
    HeaderProviderConfig,
    NoneProviderConfig,
    SignatureVerificationConfig,
    parse_auth_config,
    parse_header_provider_config,
    parse_none_provider_config,
)
from .header_provider import HeaderProvider
from .null_provider import NullProvider
from .permissions import Permissions, has_permission, parse_role_permissions
from .providers import AuthenticationError, AuthProvider, AuthUser, build_provider

__all__ = [
    "AuthConfig",
    "AuthProvider",
    "AuthUser",
    "AuthenticationError",
    "HeaderProvider",
    "HeaderProviderConfig",
    "NoneProviderConfig",
    "NullProvider",
    "Permissions",
    "SignatureVerificationConfig",
    "build_provider",
    "has_permission",
    "parse_auth_config",
    "parse_header_provider_config",
    "parse_none_provider_config",
    "parse_role_permissions",
]
