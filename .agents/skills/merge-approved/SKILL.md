---
name: merge-approved
description: Perform the guarded final squash merge only after the user explicitly approves the exact HEAD SHA previously presented as MERGE_READY.
---


# Merge Approved

Use only after an explicit user statement approving merge.

The approval must refer to the exact HEAD SHA most recently presented as MERGE_READY.
Do not silently refresh approval to a newer SHA.

Invoke:

```powershell
pwsh -NoProfile -File scripts/agent/merge-task.ps1 `
  -PrNumber <approved-pr-number> `
  -ExpectedHeadSha "<approved-head-sha>"
```

The wrapper revalidates PR identity, CI, review state, mergeability, and exact HEAD before merging.

If HEAD changed, stop and return to the review/merge-ready workflow.
Do not ask the user to approve an unreviewed replacement SHA.

After success, report:
- merged PR URL
- merged SHA reviewed/approved
- squash merge status
- local cleanup status

