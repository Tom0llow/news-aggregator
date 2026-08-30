---
name: create-pr
description: Create a guarded GitHub PR for an already validated guarded task branch. Internal building block for autonomous-task; never merge.
---


# Create PR

Use only the guarded wrapper:

```powershell
pwsh -NoProfile -File scripts/agent/create-pr.ps1 -Title "<title>" -Body "<body>"
```

Before creation ensure:
- local validation passes
- guarded commit exists
- guarded push completed
- working tree is clean

PR body:

```markdown
## Summary
- ...

## Validation
- ...

## Architecture / ADR
- ...

## Risks / Notes
- ...
```

Never merge.

