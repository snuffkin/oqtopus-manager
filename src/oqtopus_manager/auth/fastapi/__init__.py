"""FastAPI integration for the auth package."""

from .depends import CurrentUser, get_current_user, require_permission
from .middleware import AuthMiddleware

__all__ = ["AuthMiddleware", "CurrentUser", "get_current_user", "require_permission"]
