# /new-editor

Add the file-edit pattern (lock / edit / diff / save) for a new editable file.

## Arguments

`$ARGUMENTS` format: `<url-prefix> <which-key> <file-basename> <template-file>`

Example:
```
/new-editor /environments/{name}/services/{service}/config  extra  extra.yaml  environments/service_config.html
```

- `url-prefix`: URL base for the 4 POST routes (may contain path params like `{name}`)
- `which-key`: identifier used in route path and JS (e.g. `extra`)
- `file-basename`: actual filename on disk (e.g. `extra.yaml`)
- `template-file`: template path relative to `src/oqtopus_manager/templates/`

## What to implement

### 1. Backend routes (follow CLAUDE.md "File-Edit Pattern")

Add these 4 thin route handlers to the appropriate router. Each handler calls the shared helpers from `environments.py` (see CLAUDE.md "Shared Helpers"):

```
POST <url-prefix>/<which-key>/force-unlock  → _force_unlock_file(lock_path)
POST <url-prefix>/<which-key>/lock          → _acquire_file_lock(lock_path, timeout)
POST <url-prefix>/<which-key>/unlock        → _release_file_lock(lock_path, token, timeout)
POST <url-prefix>/<which-key>/save          → _save_file(file_path, lock_path, content, token, timeout)
```

- Lock file: `{filename}.lock` alongside the target file
- `token` comes from the request body (Form field)
- `timeout` comes from `cfg.file_edit_lock_timeout_sec`

Do NOT re-implement lock/save logic inline — use the shared helpers.

### 2. Template editor section (follow CLAUDE.md "File-Edit Pattern")

Add a `<details>` editor to `<template-file>`:

- If `<template-file>` is **`service_config.html`** (or another page that already uses the `editor_section` macro): add a `{{ editor_section(...) }}` call — do NOT copy HTML blocks.
- If the page has **multiple editors but no macro yet**: add the `editor_section` macro first, then call it.
- If the page has **a single editor** (e.g. `dotenv.html`): inline functions are fine.

Use `makeEditor(opts)` factory for JS if the page already has other editors; otherwise inline functions are fine (see `dotenv.html`).

Prefix all DOM IDs with a short unique prefix derived from `<which-key>` (e.g. `extra-view`, `extra-edit`, `extra-edit-btn`).

Follow CLAUDE.md exactly for:
- Button styles and order
- Lock badge markup
- Lock state visibility rules
- View / Edit / Diff section structure

### 3. Verify

After implementing, check that:
- Lock state table from CLAUDE.md is respected (Edit hidden when other-user lock, etc.)
- Button styles match the conventions table in CLAUDE.md
- JS wires up to the new URL prefix correctly
