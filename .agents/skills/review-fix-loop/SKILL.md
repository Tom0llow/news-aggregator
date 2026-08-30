---
name: review-fix-loop
description: Bounded local implementer -> reviewer -> fixer -> reviewer workflow. Internal building block for autonomous-task; it does not commit, push, create a PR, or merge.
---


# Local Review/Fix Loop

1. Spawn `implementer` for the task.
2. Inspect the resulting complete diff.
3. Spawn a fresh read-only `reviewer`.
4. Validate findings.
5. For validated P0/P1/P2, spawn `fixer`.
6. Re-review the complete diff with a fresh reviewer.
7. Maximum two fixer rounds.
8. Return unresolved findings to the coordinator.

Do not commit, push, create a PR, or merge.

