# OQTOPUS Manager — Development Guide

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

Every editable file uses the same lock/edit/diff/save flow. The canonical reference implementation is **`dotenv.html`** + the dotenv routes in **`environments.py`**.

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

### Backend routes (per editable file)

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

## Naming

- Lock/edit route handlers: `force_unlock_*`, `acquire_*_lock`, `release_*_lock`, `save_*`
- Template IDs for multi-editor pages: `{short-prefix}-{element}` (e.g. `cfg-edit-btn`, `log-lock-badge`)

---

## Route → Template Map

| URL | Template |
|---|---|
| `GET /environments` | `environments/list.html` |
| `GET /environments/new` | `environments/new.html` |
| `GET /environments/{name}` (default) | `environments/detail.html` |
| `GET /environments/{name}` (template=backend) | `environments/backend_detail.html` |
| `GET /environments/{name}/dotenv` | `environments/dotenv.html` |
| `GET /environments/{name}/services/{service}/config` | `environments/service_config.html` |
| `GET /environments/{name}/services/{service}/log` | `environments/service_log.html` |
| `GET /settings` | `app_settings.html` |
| `GET /browse` | `browse/_picker.html` |

### Template Implementation Status

| `template` value | Detail template | Status |
|---|---|---|
| `backend` | `environments/backend_detail.html` | Implemented |
| (others) | `environments/detail.html` | Stub — shows name/template/root only |

To add a new template type, use `/new-template <name>`.

---

## Router Files

| File | URL prefix | Purpose |
|---|---|---|
| `routers/environments.py` | `/environments` | Environment CRUD, dotenv, service config/log, lock routes |
| `routers/backend.py` | `/environments` | SSE backend commands, component versions JSON |
| `routers/app_settings.py` | `/settings` | App settings page |
| `routers/browse.py` | `/browse` | File/directory browser |

Template dispatch: `_DETAIL_TEMPLATE` dict in `environments.py` maps `env.template` → template path. `get_environment` route builds template-specific context in `if env.template == "..."` blocks.

---

## Environment Directory Structure

```
{env.root_path}/          # default: {default_environment_base_path}/{name}/
  .env                    # environment variables (editable via dotenv page)
  .metadata               # JSON: engine_version, tranqu_version, gateway_version
  config/
    {service}/
      config.yaml         # service config (editable via service_config page)
      logging.yaml        # logging config (editable via service_config page)
  logs/
    {service}.log         # service log (viewable via service_log page)
```

Lock files are stored alongside the target file as `{filename}.lock`.
Backup files are stored as `{filename}.{yyyymmddhhmmss}`.

---

## Environment Model

```python
class Environment(BaseModel):
    name: str          # validated: ^[a-z0-9][a-z0-9_.:-]*$
    template: str      # e.g. "backend"
    root_path: pathlib.Path | None = None  # None → base_path / name
```

`env.resolved_root_path(base_path)` returns the effective root path.
