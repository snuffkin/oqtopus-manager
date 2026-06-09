"""Null Object provider that disables authentication."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from oqtopus_manager.auth.base import AuthProvider, AuthUser

if TYPE_CHECKING:
    from fastapi import Request


class NullProvider(AuthProvider):
    """No-op provider for ``provider: none``; passes every request without a user."""

    @override
    async def authenticate(self, request: Request) -> AuthUser | None:
        """Return ``None`` for every request (authentication is disabled).

        Returns:
            Always ``None``.

        """
        return None
