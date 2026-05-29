# /review-conventions

Review recent work and propose improvements to CLAUDE.md and slash commands. Do not make any changes until the user approves.

## What to do

### 1. Gather context

- Run `git log --oneline -30` to see recent commits
- Read `CLAUDE.md`
- Read all files in `.claude/commands/`
- Read `.claude/memory/MEMORY.md` and any linked memory files

### 2. Identify improvement candidates

Look for gaps between what is documented and what the codebase actually does:

- **CLAUDE.md**: conventions that are missing, outdated, or inconsistent with current code (e.g. new button styles, new route patterns, new file-edit flows added but not documented)
- **Slash commands**: tasks that were done repeatedly in recent commits but have no command, or existing commands whose steps no longer match the current implementation
- **Memory**: feedback or project notes that should be reflected in CLAUDE.md to avoid repeating the same corrections

### 3. Present proposals — do not apply yet

Output a structured list of proposed changes in this format:

```
## Proposed changes

### CLAUDE.md
- [ ] <what to add / change / remove> — reason: <why>
...

### Slash commands
- [ ] <command name>: <what to add / update / create> — reason: <why>
...

### No changes needed
- <area>: already up to date
...
```

### 4. Ask for approval

After presenting the list, ask: "Which of these would you like to apply?"

Only implement the items the user explicitly confirms. Apply them one by one and show a brief diff summary for each.
