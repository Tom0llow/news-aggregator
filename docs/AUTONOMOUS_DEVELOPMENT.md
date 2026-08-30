# Autonomous Development Workflow

## Goal

Normal successful operation:

```text
1. Human: provide requirement
2. Human: approve/reject exact MERGE_READY HEAD
```

Everything between those points is bounded automation.

## Security model

Ordinary `workspace-write` sandbox commands have shell network access disabled.

Git/GitHub operations that need the network run outside the sandbox only through:

- narrowly allow-listed read-only `gh` commands, or
- guarded `scripts/agent/*.ps1` wrappers.

This is intentional. Do not solve GitHub connectivity by broadly opening the
workspace sandbox or by exposing all TOKEN/SECRET environment variables.

If Codex reports:

```text
proxyconnect tcp: dial tcp 127.0.0.1:9
```

for a guarded GitHub wrapper, the wrapper was not matched by the active
exec-policy and fell back into the offline sandbox. Reload/restart Codex after
updating `.codex/rules/default.rules`; do not treat that message as proof that
the GitHub token is invalid.

## Runtime lifecycle

```text
requirement
  ↓
host-side GitHub/repository/baseline-CI preflight
  ↓
guarded agent/* branch from fresh origin/main
  ↓
implementer
  ↓
independent reviewer
  ↓
bounded fixer / fresh review
  ↓
Ruff / mypy / pytest
  ↓
guarded commit + push + PR
  ↓
Quality + Test
  ├─ fail → CI analyst → bounded fixer → repush
  └─ pass
  ↓
fresh full-PR reviewer
  ├─ P0/P1/P2 → fixer → CI → fresh review
  └─ clean
  ↓
MERGE_READY exact HEAD
  ↓
human exact-HEAD approval
  ↓
guarded squash merge
```

## Baseline requirement

`origin/main` CI must already be green before an unrelated autonomous task
starts.

This prevents the agent from confusing pre-existing infrastructure failures with
task regressions.

## GitHub authentication

Do not use sandboxed `gh auth status` as the workflow's source of truth.

The guarded preflight performs a real API request:

```text
gh api user
```

from the allow-listed host execution context.

## Repository policy

Expected server-side policy:

- PR required for changes to `main`
- GitHub approving reviewers required: 0
- required checks: `Quality`, `Test`
- strict status checks
- admins also protected
- linear history
- conversations resolved
- force push disabled
- branch deletion disabled
- squash merge enabled
- merge-commit/rebase-merge disabled
- merged branches automatically deleted

Configure/verify once from a trusted admin terminal:

```powershell
pwsh -NoProfile -File scripts/github/configure-main-protection.ps1
pwsh -NoProfile -File scripts/github/verify-main-protection.ps1
```

## Machine setup

Required:

- Git
- GitHub CLI
- PowerShell 7 (`pwsh`)
- Python 3.11
- uv
- VS Code + Codex

Authenticate GitHub once from the host:

```powershell
gh auth login
gh auth setup-git
gh api user --jq .login
```

After changing `.codex/config.toml` or `.codex/rules/*.rules`, restart/reload the
Codex session so project rules are re-read.

## Repair loop limits

| Loop | Max fixer rounds |
| --- | ---: |
| Local review | 2 |
| CI repair | 2 |
| Final PR review | 2 |

Exhaustion returns `BLOCKED` with evidence.

## Stale task state

The workflow intentionally supports one active writable task per worktree.

If startup reports an existing task state, do not overwrite it.

Only after confirming there is no active task may a human remove the stale
state path returned by:

```powershell
git rev-parse --git-path codex-task.json
```

## Final merge

`merge-task.ps1` rechecks:

- recorded PR identity
- exact MERGE_READY SHA
- PR HEAD unchanged
- mergeability/CLEAN state
- `Quality` and `Test` present
- all checks passing/skipping

It then performs a squash merge and cleans up the task branch/state.
