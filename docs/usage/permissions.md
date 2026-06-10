# Permissions

OQTOPUS Manager uses a permission-based access control model.
Roles are mapped to sets of permissions, and each API endpoint or UI element requires a specific permission.

## Design conventions

### Verb vocabulary

| Verb | Meaning | Examples |
|------|---------|---------|
| `get` | Read (list and detail combined) | view list, view detail page |
| `create` | Create a new resource | new form, submit create, init stream |
| `update` | Modify an existing resource | save edited file, change settings |
| `delete` | Remove a resource | delete environment |
| `manage` | Operational control of a sub-resource | start/stop services, install components |

### Format

```text
<resource>.<action>
<resource>.<sub-resource>.<action>
```

**Examples:** `environment.get`, `environment.config.update`, `environment.service.manage`

## Permission list

| Permission | Description |
|---|---|
| `environment.get` | View environment list, detail, settings, and component versions |
| `environment.create` | Create a new environment (form, submit, init stream) |
| `environment.delete` | Delete an environment |
| `environment.config.get` | View `.env`, service config, and topology JSON files |
| `environment.config.update` | Edit and save configuration files |
| `environment.log.get` | View, stream, and download service logs |
| `environment.component.manage` | Manage components: install, uninstall, update, versions, build |
| `environment.service.manage` | Control services: start, stop, restart, status, info |
| `app_settings.get` | View OQTOPUS Manager configuration |
| `app_settings.update` | Edit OQTOPUS Manager configuration *(admin only)* |

## Role mapping

| Permission | operator | admin |
|---|:---:|:---:|
| `environment.get` | ✓ | ✓ |
| `environment.create` | ✓ | ✓ |
| `environment.delete` | ✓ | ✓ |
| `environment.config.get` | ✓ | ✓ |
| `environment.config.update` | ✓ | ✓ |
| `environment.log.get` | ✓ | ✓ |
| `environment.service.manage` | ✓ | ✓ |
| `environment.component.manage` | ✓ | ✓ |
| `app_settings.get` | ✓ | ✓ |
| `app_settings.update` | | ✓ |

`admin` is a superset of `operator` — every permission held by `operator` is also held by `admin`.

## Endpoints without permissions

Two endpoints intentionally have no `require_permission()` dependency:

| Endpoint | Reason |
|---|---|
| `GET /me` | Shows the authenticated user's own account information. Any authenticated user may view their own identity — no additional permission is needed. The route is only registered when `provider != "none"`, so unauthenticated access is already prevented. |
| `GET /debug` | Already gated by the `enable_debug_endpoint: true` configuration flag. Enabling this flag is a conscious administrative decision, so adding a permission check would create redundant double management. It is a development-only tool and is never registered in production unless explicitly configured. |

## Implementation

Permissions are defined in [`auth/permissions.py`](../../src/oqtopus_manager/auth/permissions.py).
The `require_permission()` FastAPI dependency in `auth/fastapi/depends.py` enforces permissions on each route.

When authentication is disabled (`provider: none`), a virtual admin user is used so that
all permissions are granted and the application behaves identically to a real admin session.
