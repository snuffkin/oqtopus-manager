# /find-refactoring

Scan the Python and HTML codebase for refactoring and consolidation opportunities. List findings only — do not make any changes.

## Arguments

`$ARGUMENTS` (optional): scope hint, e.g. `routers` or `templates` or `environments`. If omitted, scan everything.

## What to do

### 1. Scan Python files (`src/`)

Look for:

- **Duplicate logic**: similar blocks in multiple route handlers or helpers that could be extracted into a shared function
- **Long functions**: functions with many local variables or deeply nested branches that could be split
- **Inconsistent patterns**: places where the same task (e.g. reading a lock file, building a context dict) is done differently in different files
- **Dead code**: imports, variables, or functions that appear unused

Focus on `routers/` and `models/`. Skip generated or vendored files.

### 2. Scan HTML templates (`src/.../templates/`)

Look for:

- **Repeated markup blocks**: identical or near-identical HTML snippets (banner SVG, button groups, lock badge) copy-pasted across multiple templates
- **Inline JS that duplicates logic**: JS functions in multiple templates that do the same thing and could live in a shared `<script>` or JS file
- **Inconsistencies with CLAUDE.md conventions**: button classes, SVG sizes, or lock badge markup that differs from the documented standard

### 3. Present findings — do not change anything

Output a prioritised list:

```
## Refactoring candidates

### High value (duplicated logic, easy to extract)
- [ ] <file(s)>: <what> — <why it matters>
...

### Medium value (inconsistency or cleanup)
- [ ] <file(s)>: <what> — <why it matters>
...

### Low value / optional
- [ ] <file(s)>: <what> — <why it matters>
...

### No issues found
- <area>: looks clean
```

Do not implement any of these. If the user wants to act on a finding, they will ask separately.

## Known non-issues (do not suggest)

- **`dotenv.html` への `makeEditor()` 移行**: CLAUDE.md の規約で「single editor はインライン関数で良い」と明記されているため対象外。
