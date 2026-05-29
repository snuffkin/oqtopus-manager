"""Server-side directory browser for the path picker."""

import pathlib

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/browse", tags=["browse"])


@router.get("", response_class=HTMLResponse)
async def browse(request: Request, path: str = "") -> HTMLResponse:
    """Return an HTML directory listing for the given path.

    Defaults to the current working directory when *path* is not provided.

    Returns:
        HTMLResponse with the directory listing.

    """
    current = pathlib.Path(path).resolve() if path else pathlib.Path.cwd()  # noqa: ASYNC240

    if not current.is_dir():
        current = pathlib.Path.cwd()

    try:
        entries = sorted(
            (e for e in current.iterdir() if e.is_dir() and not e.name.startswith(".")),
            key=lambda e: e.name,
        )
    except PermissionError:
        entries = []

    parent = current.parent if current != current.parent else None

    return request.app.state.templates.TemplateResponse(
        request,
        "browse/_picker.html",
        {"current": current, "entries": entries, "parent": parent},
    )
