"""FastAPI integration for the auth package."""

from .middleware import AuthMiddleware

__all__ = ["AuthMiddleware"]
