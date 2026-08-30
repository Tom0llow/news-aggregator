---
name: pr-review
description: Run the final independent read-only review of the complete current pull request; fix validated P0/P1/P2 findings with bounded re-review. Intended for autonomous-task.
---


# Final PR Review

The PR review is independent from the initial local review.

## Loop bound

Maximum two fixer rounds.

## Procedure

1. Capture current PR number and HEAD SHA.
2. Ensure CI for that HEAD is passing.
3. Spawn a fresh `pr_reviewer` read-only with:
   - original requirement and acceptance criteria
   - PR number
   - exact HEAD SHA
   - relevant architecture/ADR context
4. The reviewer must inspect the complete PR diff and current code.
5. Coordinator validates each finding.

Classification:

```text
validated P0/P1/P2 -> must fix before MERGE_READY
P3 -> may remain if non-blocking and reported
incorrect/not reproducible -> reject with evidence
needs product decision -> BLOCKED
```

For validated blocking findings:

1. spawn `fixer`
2. run focused + repository validation
3. guarded commit
4. guarded push
5. wait for CI to pass on the new HEAD
6. spawn a fresh `pr_reviewer` for the complete PR

Never treat an old review as approval for a new HEAD.

