# /new-template

Scaffold a new environment template type.

## Arguments

`$ARGUMENTS`: template name (lowercase, matches `env.template` value)

Example:
```
/new-template simulator
```

## What to implement

### 1. Add to the dispatch table

In `src/oqtopus_manager/routers/environments.py`, add the new template to `_DETAIL_TEMPLATE`:

```python
_DETAIL_TEMPLATE: dict[str, str] = {
    "backend": "environments/backend_detail.html",
    "<name>": "environments/<name>_detail.html",   # ← add this
}
```

### 2. Add context building in `get_environment`

In the `get_environment` route handler (same file), add an `elif env.template == "<name>"` block after the existing `if env.template == "backend"` block to populate any template-specific context variables.

### 3. Create the detail template

Create `src/oqtopus_manager/templates/environments/<name>_detail.html`.

Start from the skeleton in `detail.html` (which shows name / template / root path). Extend it with sections appropriate to the new template type.

Follow all CLAUDE.md conventions:
- Page banner: same blue gradient as `backend_detail.html`
- Card sections: `<details>` with `data-sec` attribute, same shadow/border style
- Button styles: follow the conventions table exactly
- If any editable files are needed, use `/new-editor` to add them

### 4. Register any new CLI commands

If the new template introduces new `oqtopus` subcommands, add them to `_build_args()` in `src/oqtopus_manager/routers/backend.py` (or create a new router file if the command surface is large).

### 5. Update CLAUDE.md

Add the new template to the "Template Implementation Status" table in CLAUDE.md.
