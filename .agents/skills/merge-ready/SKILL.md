---
name: merge-ready
description: Evaluate whether the current guarded PR is safe to present for human merge approval. Read-only; never merge.
---


# Merge Ready

Run only after implementation, CI, and final PR review are complete.

Execute:

```powershell
pwsh -NoProfile -File scripts/agent/merge-ready.ps1 -PrNumber <N>
```

A successful gate requires:

- guarded task branch/PR identity matches
- clean local working tree
- local HEAD == remote task branch == PR HEAD
- PR open and non-draft
- mergeable and CLEAN
- no blocking GitHub review decision
- at least one CI/status check
- all checks pass/skip

Also require from the coordinator's own workflow state:

- no validated P0/P1/P2 final AI review findings remain
- acceptance criteria are satisfied
- no unresolved architecture/security blocker exists

If ready, present the exact SHA to the user for merge approval.

Never merge from this skill.

