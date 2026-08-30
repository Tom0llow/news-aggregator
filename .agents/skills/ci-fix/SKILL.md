---
name: ci-fix
description: Diagnose and repair failing GitHub Actions checks for the current guarded PR, then commit/push and re-run CI. Intended for the autonomous-task coordinator.
---


# CI Fix

Use only for the current guarded task PR.

## Loop bound

Maximum two CI fixer rounds.

## Procedure

1. Confirm the failing PR number and exact HEAD SHA.
2. Spawn `ci_analyst` read-only.
3. Ask it to inspect:
   - `gh pr checks <N>`
   - relevant `gh run list`
   - `gh run view <run> --log-failed`
   - changed code/configuration
4. Validate the diagnosis.
5. If failure is task-related and fixable, spawn `fixer` with only the validated diagnosis.
6. Run focused validation, then repository-level checks.
7. If code changed:
   ```powershell
   pwsh -NoProfile -File scripts/agent/commit-task.ps1 -Message "<fix(...) or ci(...): ...>"
   pwsh -NoProfile -File scripts/agent/push-task.ps1
   ```
8. Wait again:
   ```powershell
   pwsh -NoProfile -File scripts/agent/wait-ci.ps1 -PrNumber <N>
   ```

If a failure is infrastructure/external and not caused by the patch, do not invent a code change. Report BLOCKED with evidence.

Never disable CI, remove tests, lower coverage, or weaken checks merely to obtain green status.

