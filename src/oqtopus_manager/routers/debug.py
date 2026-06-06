"""Debug route: exposes request headers and JWT payload for development inspection."""

from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

_JWT_PARTS_MIN = 2


def _decode_jwt_without_verification(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < _JWT_PARTS_MIN:
        return {"error": "Invalid JWT format"}

    header_b64, payload_b64 = parts[0], parts[1]

    def decode_part(value: str) -> dict:
        padded = value + "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode(padded)
        return json.loads(raw)

    return {
        "header": decode_part(header_b64),
        "payload": decode_part(payload_b64),
    }


@router.get("/debug", response_class=HTMLResponse)
async def debug_page(request: Request) -> HTMLResponse:
    """Render request headers, mapped roles, and decoded JWT for debugging.

    Returns:
        The rendered debug.html template.

    """
    headers = sorted(request.headers.items())

    jwt_result: dict = {}
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth[len("bearer ") :]
        try:
            jwt_result = _decode_jwt_without_verification(token)
        except Exception as e:  # noqa: BLE001
            jwt_result = {"error": str(e)}

    return request.app.state.templates.TemplateResponse(
        request,
        "debug.html",
        {
            "headers": headers,
            "jwt": jwt_result,
        },
    )
