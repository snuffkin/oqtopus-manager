"""FastAPI dependencies for authentication and authorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Request

from ..base import AuthUser  # noqa: TID252
from ..permissions import Permissions, has_permission  # noqa: TID252

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsType


def get_current_user(request: Request) -> AuthUser | None:
    """Extract the authenticated user from request state (set by AuthMiddleware).

    Returns:
        The authenticated user, or None when no user is present.

    """
    return request.state.user


CurrentUser = Annotated[AuthUser | None, Depends(get_current_user)]


class FastAPIPermissions(Permissions):
    """FastAPI-aware permission checker that extends :class:`Permissions`.

    Adds :meth:`require`, a FastAPI dependency factory, to the framework-agnostic
    :meth:`has_permission` inherited from the base class.

    Create one instance per application and use it as follows::

        permissions = FastAPIPermissions(role_permissions)

        @router.get("/settings", dependencies=[permissions.require("app_settings.get")])
        async def settings(request: Request) -> HTMLResponse:
            can_edit = permissions.has_permission(
                request.state.user, "app_settings.update"
            )

    """

    def require(self, permission: str) -> DependsType:
        """Return a FastAPI dependency that raises 403 if the permission is absent.

        Returns:
            A ``Depends`` instance suitable for ``dependencies=[...]``.

        """
        role_permissions = self._role_permissions

        def check(user: CurrentUser) -> AuthUser | None:
            if not has_permission(user, permission, role_permissions):
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return user

        return Depends(check)


def require_permission(permission: str) -> DependsType:
    """Return a FastAPI dependency that enforces the given permission.

    Reads the :class:`FastAPIPermissions` instance from
    ``request.app.state.permissions``.  This is a convenience function for
    applications where route modules are imported before the
    ``FastAPIPermissions`` instance is constructed (e.g. when routes are
    registered inside an application factory).

    For new projects that control the import order, prefer
    ``FastAPIPermissions.require()`` instead.

    Returns:
        A ``Depends`` instance that raises 403 if the check fails.

    """

    def check(request: Request, user: CurrentUser) -> AuthUser | None:
        permissions: FastAPIPermissions = request.app.state.permissions
        if not permissions.has_permission(user, permission):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return Depends(check)
