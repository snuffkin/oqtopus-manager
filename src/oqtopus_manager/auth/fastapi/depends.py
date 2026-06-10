"""FastAPI dependencies for authentication and authorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Request

from ..base import AuthUser  # noqa: TID252
from ..permissions import has_permission  # noqa: TID252

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsType


def get_current_user(request: Request) -> AuthUser | None:
    """Extract the authenticated user from request state (set by AuthMiddleware).

    Returns:
        The authenticated user, or None when no user is present.

    """
    return request.state.user


CurrentUser = Annotated[AuthUser | None, Depends(get_current_user)]


def require_permission(permission: str) -> DependsType:
    """Return a FastAPI dependency that enforces the given permission.

    Returns:
        A FastAPI ``Depends`` instance that raises 403 if the check fails.

    """

    def check(request: Request, user: CurrentUser) -> AuthUser | None:
        role_permissions: dict[str, frozenset[str]] = request.app.state.role_permissions
        if not has_permission(user, permission, role_permissions):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return Depends(check)
