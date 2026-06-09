"""FastAPI middleware that delegates authentication to the configured provider."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from fastapi.responses import HTMLResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from oqtopus_manager.auth.providers import AuthenticationError, build_provider

if TYPE_CHECKING:
    from fastapi import Request
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp

    from oqtopus_manager.auth.config import AuthConfig


class AuthMiddleware(BaseHTTPMiddleware):
    """Delegates authentication to the configured provider on every request."""

    def __init__(self, app: ASGIApp, auth_cfg: AuthConfig) -> None:
        super().__init__(app)
        self._provider = build_provider(auth_cfg)

    @override
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Delegate to the provider and return 403 on AuthenticationError.

        Returns:
            403 response if the provider raises ``AuthenticationError``; otherwise
            the downstream response with ``request.state.user`` set.

        """
        request.state.user = None
        try:
            request.state.user = await self._provider.authenticate(request)
        except AuthenticationError as e:
            return HTMLResponse(f"403 Forbidden: {e.reason}", status_code=403)
        return await call_next(request)
