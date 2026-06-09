"""Shared authentication base types used by all providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request


@dataclass
class AuthUser:
    """Authenticated user extracted from JWT claims."""

    account: str
    roles: list[str] = field(default_factory=list)
    raw_groups: list[str] = field(default_factory=list)

    @property
    def role(self) -> str:
        """Return the primary role for backward-compatible single-role display."""
        return self.roles[0] if self.roles else ""


class AuthenticationError(Exception):
    """Raised by a provider when the request should be rejected with 403."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AuthProvider(ABC):
    """Abstract base for authentication providers."""

    @abstractmethod
    async def authenticate(self, request: Request) -> AuthUser | None:
        """Authenticate the request.

        Returns:
            ``AuthUser`` on success, or ``None`` when the provider is disabled
            (Null Object — passes the request through without a user).

        Raises:
            AuthenticationError: If the request should be rejected with 403.

        """
