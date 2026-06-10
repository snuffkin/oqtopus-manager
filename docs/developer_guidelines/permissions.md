# Permissions and FastAPIPermissions

This page describes the `Permissions` and `FastAPIPermissions` classes
provided by the `auth` package.

## Overview

The permission system is split into two layers:

| Class | Package | Responsibility |
|---|---|---|
| `Permissions` | `auth` (framework-agnostic) | Stores resolved role-to-permission mapping; provides `has_permission()` |
| `FastAPIPermissions` | `auth.fastapi` (FastAPI-specific) | Inherits `Permissions`; adds `require()` for use as a FastAPI dependency |

## Permissions

Defined in `auth/permissions.py`. No FastAPI dependency.

```python
from oqtopus_manager.auth import Permissions

permissions = Permissions(role_permissions)

# Check a permission in a route handler or template context
can_edit = permissions.has_permission(user, "app_settings.update")
```

### Constructor

```python
Permissions(role_permissions: dict[str, frozenset[str]])
```

Pass the resolved role-to-permission mapping produced by `parse_role_permissions()`.

### Methods

| Method | Description |
|---|---|
| `has_permission(user, permission)` | Returns `True` if the user holds any role that grants the permission. |

## FastAPIPermissions

Defined in `auth/fastapi/depends.py`. Inherits `Permissions` and adds
the `require()` dependency factory for FastAPI routes.

```python
from oqtopus_manager.auth.fastapi import FastAPIPermissions

permissions = FastAPIPermissions(role_permissions)

# Use as a route dependency
@router.get("/settings", dependencies=[permissions.require("app_settings.get")])
async def settings_page(request: Request) -> HTMLResponse:
    can_edit = permissions.has_permission(request.state.user, "app_settings.update")
```

### Additional method

| Method | Description |
|---|---|
| `require(permission)` | Returns a `Depends` instance that raises `403` if the user lacks the permission. |

## Usage in OQTOPUS Manager

`FastAPIPermissions` is instantiated once in `main.py` and stored in
`app.state.permissions`:

```python
app.state.permissions = FastAPIPermissions(cfg.role_permissions)
```

Route files use `require_permission()` (a convenience function that reads from
`app.state.permissions`) because route decorators run at import time — before
the `FastAPIPermissions` instance is constructed.

```python
from oqtopus_manager.auth.fastapi import require_permission

@router.get("", dependencies=[require_permission("environment.get")])
async def list_environments(request: Request) -> HTMLResponse:
    ...
```

## Producing role_permissions

Use `parse_role_permissions()` from `auth.permissions` to convert the raw
`permissions:` section of `config.yaml` into the resolved mapping:

```python
from oqtopus_manager.auth import parse_role_permissions

role_permissions = parse_role_permissions(raw["permissions"])
# → dict[str, frozenset[str]]
```
