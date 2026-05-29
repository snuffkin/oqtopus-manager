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

Add these 4 routes to the appropriate router, modelled on `force_unlock_service_config` / `acquire_service_config_lock` / `release_service_config_lock` / `save_service_config` in `environments.py`.

```
POST <url-prefix>/<which-key>/force-unlock
POST <url-prefix>/<which-key>/lock
POST <url-prefix>/<which-key>/unlock
POST <url-prefix>/<which-key>/save
```

- Lock file: `{filename}.lock` alongside the target file
- Backup naming: `{filename}.{yyyymmddhhmmss}`
- Lock format: `{uuid}\n{unix_timestamp}`
- Use `_check_lock()` helper (already defined in environments.py)
- `lock` returns `{ok, token, acquired_ts}` or 409
- `save` validates token, backs up, writes, releases lock

### 2. Template editor section (follow CLAUDE.md "File-Edit Pattern")

Add a `<details>` section to `<template-file>` modelled on the existing editors in `service_config.html`.

Use `makeEditor(opts)` factory if the page already has other editors; otherwise inline functions are fine (see `dotenv.html`).

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
