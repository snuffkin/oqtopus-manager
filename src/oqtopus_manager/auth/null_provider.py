"""Null Object provider that disables authentication."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from oqtopus_manager.auth.base import AuthProvider, AuthUser

if TYPE_CHECKING:
    from fastapi import Request

# Virtual admin user returned when authentication is disabled,
# so permission checks and templates behave identically to a real admin.
_LOCAL_ADMIN = AuthUser(account="admin_user", roles=["admin"], raw_groups=[])


class NullProvider(AuthProvider):
    """No-op provider for ``provider: none``; grants every request admin access."""

    @override
    async def authenticate(self, request: Request) -> AuthUser | None:
        """Return a virtual admin user (authentication is disabled).

        Returns:
            A synthetic admin ``AuthUser`` so that permission checks and
            template flags behave identically to a real admin session.

        """
        return _LOCAL_ADMIN
