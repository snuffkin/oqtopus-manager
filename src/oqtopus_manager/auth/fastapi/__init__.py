"""FastAPI integration for the auth package."""

from .depends import (
    CurrentUser,
    FastAPIAuthPermissions,
    get_current_user,
    require_permission,
)
from .middleware import AuthMiddleware

__all__ = [
    "AuthMiddleware",
    "CurrentUser",
    "FastAPIAuthPermissions",
    "get_current_user",
    "require_permission",
]
