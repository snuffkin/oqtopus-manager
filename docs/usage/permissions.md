# Permissions

## Overview

OQTOPUS Manager uses **permission-based access control (PBAC)**. The core idea is:

1. Each user holds one or more **roles** (e.g. `operator`, `admin`).
2. Each role is mapped to a set of **permissions** (e.g. `environment.get`, `app_settings.update`).
3. Each API endpoint and UI element declares which permission it requires.

This two-level indirection (role → permission) decouples "who the user is" from "what they can do".
Adding a new action only requires a new permission string — no role definition changes.

### Why permissions instead of roles?

A role-only model checks `if user.role == "admin"` directly in the code. This becomes fragile:
adding a new role or redistributing capabilities requires touching every check site.

With permissions, each check site declares a stable intent (`"environment.create"`) and the
role-to-permission mapping in `config.yaml` determines who can perform it.
Changing which roles have which permissions requires only a config change, not a code change.

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

Each permission string follows the `<resource>.<action>` format described above.
The table below lists all permissions **hardcoded in the application**.
Adding or removing a permission requires a code change.

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

The table below shows the **recommended default mapping** provided in `config/config.yaml.example`.
This is not fixed — you can freely change which roles exist and which permissions each role holds
by editing the `permissions:` section of your `config.yaml`
(see [Configuration — permissions](configuration.md#permissions)).

`admin` is configured as a strict superset of `operator`:
every permission `operator` holds is also held by `admin`, plus `admin` gains
`app_settings.update` to manage the application itself.

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

Role-to-permission mappings are defined in `config.yaml` under the `permissions:` key
(see [Configuration — permissions](configuration.md#permissions)).

The application reads this configuration at startup and uses the following components to enforce it:

- `auth/permissions.py` — provides `parse_role_permissions()` to parse the config and `Permissions` to check them
- `auth/fastapi/depends.py` — provides `FastAPIPermissions` and `require_permission()` to enforce permissions on each route

For details on how to use these classes, see
[Developer Guidelines — Permissions](../developer_guidelines/permissions.md).

When authentication is disabled (`provider: none`), a virtual admin user is used so that
all permissions are granted and the application behaves identically to a real admin session.
