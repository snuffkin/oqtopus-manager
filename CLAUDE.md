# OQTOPUS Manager — Development Guide

## Verification (run after every change)

- **After code changes**: run `make verify` (= format + lint + test)
- **After documentation changes**: run `make docs-lint`

Run these automatically — do not wait to be asked.

---

## Code Comments

Add a short English inline comment whenever the **why** is non-obvious: hidden constraints, subtle invariants, workarounds, or logic that would surprise a reader. One line max. Do not explain what the code does — only why.

Examples of comment-worthy blocks:
- A fallback value chosen for a non-obvious reason (`# Default to epoch 0 so missing timestamps are always stale`)
- A guard against a race condition or edge case
- A design decision that affects behavior (`# Persist absolute path so the entry is cwd-independent`)
- A non-obvious API behavior (`# relative_to() raises ValueError when path is outside base`)

---

## Stack

- **Backend**: FastAPI + Jinja2 templates
- **Frontend**: Tailwind CSS (CDN) + DaisyUI + HTMX
- **Syntax highlighting**: highlight.js 11.9 (github theme)

## UI Conventions

### Button styles

All toolbar/summary-row buttons follow these rules — do not invent new variants:

| Purpose | Class | Notes |
|---|---|---|
| Page-level CTA (New Environment…) | `btn btn-primary btn-outline gap-2` | White bg, blue border/text |
| Toolbar action (Edit, Connect…) | `btn btn-ghost btn-sm text-gray-400 hover:text-gray-600 gap-1` | Always add an SVG icon |
| Destructive action (Force Unlock) | `btn btn-ghost btn-sm gap-1` + `style="color:#dc2626;"` | Open-lock SVG icon |
| Secondary ghost (Preview & Save, Cancel) | `btn btn-ghost btn-sm text-gray-400 hover:text-gray-600 gap-1` / `text-gray-500` | Icon on Preview & Save |
| Diff section (Confirm Save) | `btn btn-sm btn-success btn-outline` | |
| Diff section (Back to Edit) | `btn btn-sm btn-outline` | |
| Diff section (Cancel) | `btn btn-sm btn-outline btn-error` | |
| Delete / destructive row action | `btn btn-error btn-sm btn-outline gap-1.5` | |

**Rule: all buttons use white background (outline style). Never use filled `btn-primary` alone.**

**Never use `btn-xs` for toolbar buttons.** `btn-sm` is the standard.

### Lock badge

```html
<span class="inline-flex items-center gap-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
  <!-- closed-lock SVG h-3.5 w-3.5 -->
  <span id="*-lock-badge-text"></span>
</span>
```

### SVG icon sizes

- Toolbar buttons: `h-4 w-4`
- Lock/badge icons: `h-3.5 w-3.5`

---

## File-Edit Pattern

Every editable file uses the same lock/edit/diff/save flow.

- **JS pattern reference**: `dotenv.html` (inline functions for single editor; `makeEditor()` factory for multi-editor)
- **Python route reference**: dotenv routes in `environments.py` — thin wrappers that call the shared helpers in the "Shared Helpers" section below
- **Jinja2 template reference for multi-editor pages**: `service_config.html` uses the `editor_section` macro; add new editors via a macro call, not by copying HTML blocks

### Lock state rules (always enforce)

| State | Edit | Force Unlock | Preview & Save | Cancel | Download |
|---|---|---|---|---|---|
| Idle (no lock) | visible | hidden | hidden | hidden | visible |
| Other user holds lock | **hidden** | visible | hidden | hidden | visible |
| Current user editing | hidden | hidden | visible | visible | hidden |
| Lock expired (other user's) | visible | hidden | hidden | hidden | visible |

When the countdown reaches 0 and `lockToken` is null (other user's lock), automatically restore: hide badge + Force Unlock, show Edit.

### Summary header (right side)

Buttons appear in this order, toggling visibility based on state:

1. Lock badge (amber, with countdown `Locked since … · Ns remaining`)
2. Force Unlock (hidden unless locked by another session)
3. Edit (hidden while editing)
4. Preview & Save (hidden until edit mode)
5. Cancel (hidden until edit mode)
6. Download (hidden while editing)
7. Fullscreen toggle

### Sections inside `<details>`

- **View section** (`#*-view`): highlighted `<pre><code>` — visible by default
- **Edit section** (`#*-edit`): backdrop textarea (transparent text + absolute `<pre>` highlight behind) — hidden by default
- **Diff section** (`#*-diff`): LCS line diff with CHANGES title + Confirm Save / Back to Edit / Cancel — hidden by default

### Routes (per editable file)

```
POST /{...}/force-unlock   — remove lock unconditionally
POST /{...}/lock           — acquire lock → {ok, token, acquired_ts} or 409
POST /{...}/unlock         — release lock (token required)
POST /{...}/save           — validate token, backup original, write, release lock
```

Lock file format: `{uuid}\n{unix_timestamp}` stored alongside the target file as `{filename}.lock`.
Backup naming: `{filename}.{yyyymmddhhmmss}`.

### Frontend JS pattern

Use the `makeEditor(opts)` factory (see `service_config.html`) when a page has multiple independent editors. For a single editor, inline functions are fine (see `dotenv.html`).

---

## Layout Conventions

- `html { font-size: 18px }` is set globally in `base.html` — do not override per-page.
- Pages with a full-height terminal or editor: add `main { padding-top: 0 !important; padding-bottom: 0 !important; }` in `extra_head`.
- Banner padding: `py-3` (compact, matching the reduced main padding).
- Fullscreen via CSS: `details.is-fullscreen { position: fixed !important; inset: 0 !important; z-index: 40; ... }` — sticky summary header inside.

---

## Shared Helpers

Use these helpers when implementing new routes — do not re-implement inline:

### `routers/_shared.py`

| Helper | Purpose |
|---|---|
| `_get_config(request)` | Return `request.app.state.config` |
| `_get_templates(request)` | Return `request.app.state.templates` |
| `_get_environment_or_404(name, cfg)` | Load environment by name or raise 404 |

### `routers/_file_edit.py`

| Helper / Model | Purpose |
|---|---|
| `_check_lock(lock_path, timeout)` | Read lock file state → `(is_locked, token, locked_since, locked_since_ts)` |
| `_force_unlock_file(lock_path)` | Remove lock file unconditionally → `JSONResponse` |
| `_acquire_file_lock(lock_path, timeout)` | Acquire lock → `{ok, token, acquired_ts}` or 409 |
| `_release_file_lock(lock_path, token, timeout)` | Release lock (token required) → `{ok}` or 403 |
| `_save_file(file_path, lock_path, content, token, timeout)` | Validate token, backup, write, release → `{ok}` or 4xx |
| `_UnlockBody` | Pydantic request body: `{token}` |
| `_SaveBody` | Pydantic request body: `{token, content}` |

### `routers/backend/_utils.py`

| Helper | Purpose |
|---|---|
| `_read_path_from_yaml(yaml_file, keys, env_root)` | Safely traverse nested YAML keys → `Path \| None` |

Route handlers for the file-edit pattern are thin wrappers that call the shared helpers above.

---

## Naming

- Lock/edit route handlers: `force_unlock_*`, `acquire_*_lock`, `release_*_lock`, `save_*`
- Template IDs for multi-editor pages: `{short-prefix}-{element}` (e.g. `cfg-edit-btn`, `log-lock-badge`)

---

## Route → Template Map

Each template type has its own URL prefix. Routes within a template group are in the corresponding router file.

### `/backend` — Backend template

| URL | Template / Response |
|---|---|
| `GET /backend` | `environments/list.html` (filtered to `template=backend`) |
| `GET /backend/new` | `environments/new.html` |
| `GET /backend/{name}` | `environments/backend_detail.html` |
| `GET /backend/{name}/settings-partial` | `environments/_settings_dl.html` (HTMX partial) |
| `GET /backend/{name}/dotenv` | `environments/dotenv.html` |
| `GET /backend/{name}/services/{service}/config` | `environments/service_config.html` |
| `GET /backend/{name}/services/{service}/log` | `environments/service_log.html` |
| `GET /backend/{name}/stream?cmd=...` | SSE stream |
| `GET /backend/{name}/component-versions?component=...` | JSON version list |

### `/cloud-local` — Cloud Local template

| URL | Template / Response |
|---|---|
| `GET /cloud-local` | `environments/list.html` (filtered to `template=cloud-local`) |
| `GET /cloud-local/new` | `environments/new.html` |
| `GET /cloud-local/{name}` | `environments/cloud_local_detail.html` |
| `GET /cloud-local/{name}/settings-partial` | `environments/_settings_dl.html` (HTMX partial) |
| `GET /cloud-local/{name}/dotenv` | `environments/dotenv.html` |
| `GET /cloud-local/{name}/services/{service}/log` | `environments/service_log.html` |
| `GET /cloud-local/{name}/stream?cmd=...` | SSE stream |
| `GET /cloud-local/{name}/component-versions?component=...` | JSON version list |

### Other routes

| URL | Template / Response |
|---|---|
| `GET /settings` | `app_settings.html` |
| `GET /browse` | `browse/_picker.html` |

### Template Implementation Status

| `template` value | URL prefix | Detail template | Version keys | Status |
|---|---|---|---|---|
| `backend` | `/backend` | `environments/backend_detail.html` | `engine_version`, `tranqu_version`, `gateway_version` | Implemented |
| `cloud-local` | `/cloud-local` | `environments/cloud_local_detail.html` | `cloud_version`, `frontend_version`, `admin_version` | Implemented |

---

## Router Files

| File | URL prefix | Purpose |
|---|---|---|
| `routers/_utils.py` | — | Shared helpers: `_get_config`, `_get_templates`, `_get_environment_or_404` |
| `routers/_file_edit.py` | — | Shared file-edit helpers + `_UnlockBody` / `_SaveBody` models |
| `routers/backend/list.py` | `/backend` | Environment list, new form, create, delete, init stream |
| `routers/backend/detail.py` | `/backend` | Environment detail, settings partial, oqtopus command stream, component versions |
| `routers/backend/dotenv.py` | `/backend` | .env editor, lock/save/download |
| `routers/backend/service_config.py` | `/backend` | Service config (config.yaml / logging.yaml) and topology JSON editor |
| `routers/backend/log.py` | `/backend` | Service log view, stream, download |
| `routers/cloud_local/list.py` | `/cloud-local` | Environment list, new form, create, delete, init stream |
| `routers/cloud_local/detail.py` | `/cloud-local` | Environment detail, settings partial, command stream, component versions |
| `routers/cloud_local/dotenv.py` | `/cloud-local` | .env editor, lock/save/download |
| `routers/cloud_local/log.py` | `/cloud-local` | Service log view, stream, download |
| `routers/app_settings.py` | `/settings` | App settings page |
| `routers/browse.py` | `/browse` | File/directory browser |

Each template type has its own sub-package (`routers/backend/`, `routers/cloud_local/`) organized by screen. Each sub-package exposes a `routers` list consumed by `main.py`.

To add a new template type: create a sub-package with the same screen structure, add the URL prefix to `environment_templates` in `config.yaml`, and register `pkg.routers` in `main.py`.

---

## Environment Directory Structure

### Backend (`template=backend`)

```
{env_root}/
  .env                    # environment variables (editable via dotenv page)
  .metadata               # key=value: engine_version, tranqu_version, gateway_version
  config/
    {service}/
      config.yaml         # service config (editable via service_config page)
      logging.yaml        # logging config (editable via service_config page)
  logs/
    {service}.log         # service log
```

### Cloud Local (`template=cloud-local`)

```
{env_root}/
  .env                    # environment variables (editable via dotenv page)
  .metadata               # key=value: cloud_local_cloud_version, cloud_local_frontend_version,
                          #            cloud_local_admin_version  (prefix stripped on read)
  logs/
    {service}/
      service.log         # service log (path differs from backend)
```

Lock files are stored alongside the target file as `{filename}.lock`.
Backup files are stored as `{filename}.{yyyymmddhhmmss}`.

---

## Environment Model

```python
class Environment(BaseModel):
    name: str          # validated: ^[a-z0-9][a-z0-9_.:-]*$
    template: str      # e.g. "backend", "cloud-local"
    root_path: pathlib.Path | None = None  # None → base_path / name
```

`env.resolved_root_path(base_path)` returns the effective root path.

### `config.yaml` — `environment_templates`

Controls which template types appear in the sidebar and the default redirect target:

```yaml
appearance:
  environment_templates:
    - cloud-local   # first entry = default redirect from /
    - backend
```
