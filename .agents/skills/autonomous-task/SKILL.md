---
name: autonomous-task
description: Run the full guarded coding lifecycle from a user requirement to MERGE_READY: preflight, branch, implementation, independent review/fix, commit, push, PR, CI remediation, final PR review, and readiness gate. Use for non-trivial implementation or bug-fix requests unless the user explicitly asks for local-only work.
---

# Autonomous Task Orchestrator

The intended successful lifecycle is:

```text
Human: requirement
AI: preflight -> agent/* -> implement/review/fix -> validate -> commit/push/PR
    -> CI/fix -> final PR review/fix -> MERGE_READY
Human: approve exact MERGE_READY HEAD
AI: guarded squash merge
```

Do not merge in this skill.

## Hard bounds

- writable agents run sequentially
- local review/fix: max 2 fixer rounds
- CI fix: max 2 fixer rounds per PR HEAD lineage
- final PR review fix: max 2 fixer rounds
- never recursively start another `autonomous-task`
- do not overwrite an existing guarded task state
- stop as BLOCKED instead of guessing when a material product/security decision is required

## Phase 0 — guarded host preflight

Run exactly one standalone command:

```powershell
pwsh -NoProfile -File scripts/agent/github-preflight.ps1
```

Do not replace it with `gh auth status`.

Do not chain it with `&&`, `;`, pipes, or another command.

The preflight verifies:

- GitHub API access through the host-side allow-listed wrapper
- origin/main existence
- repository/main protection policy
- current main baseline CI is green

If the error mentions `proxyconnect` or `127.0.0.1:9`, treat that as an
exec-policy/rule-loading problem, not as proof of invalid GitHub credentials.
Stop and instruct the user to reload/restart Codex after confirming the project
rules are trusted and loaded.

If baseline main CI is failing, stop. Do not start an unrelated task on a known
broken baseline.

## Phase 1 — guarded task branch

```powershell
pwsh -NoProfile -File scripts/agent/start-task.ps1 -TaskName "<short task name>"
```

Startup requires:

- clean working tree
- current local branch is `main`
- no active/stale guarded task state
- branch is created from fresh `origin/main`

## Phase 2 — implement + independent local review

Spawn `implementer` with:

- full requirement
- explicit acceptance criteria
- relevant architecture/ADR constraints
- instruction not to commit/push/PR/merge

Inspect the complete diff.

Spawn a fresh read-only `reviewer`.

Validate reviewer findings yourself.

For validated P0/P1/P2 findings, spawn `fixer`, then re-review the complete
current diff with a fresh reviewer. Maximum two fixer rounds.

P3 may remain only when non-blocking and reported.

## Phase 3 — repository validation

Run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Do not publish known task-related failures.

## Phase 4 — commit / push / PR

Use only:

```powershell
pwsh -NoProfile -File scripts/agent/commit-task.ps1 -Message "<type(scope): description>"
pwsh -NoProfile -File scripts/agent/push-task.ps1
pwsh -NoProfile -File scripts/agent/create-pr.ps1 -Title "<title>" -Body "<body>"
```

PR body must include:

- Summary
- Validation
- Architecture / ADR impact
- Risks / Notes

Capture PR number, URL, and exact HEAD SHA.

## Phase 5 — CI stabilization

```powershell
pwsh -NoProfile -File scripts/agent/wait-ci.ps1 -PrNumber <N>
```

Required checks are exactly:

- `Quality`
- `Test`

If CI fails, follow `ci-fix`. After each fix commit/push, wait again.

Stop as BLOCKED after two CI fixer rounds.

## Phase 6 — final PR review

Follow `pr-review`.

The final reviewer must inspect the complete PR at the latest exact HEAD.

Validated P0/P1/P2 findings require fix -> validation -> guarded commit/push ->
CI -> fresh full-PR review.

Never reuse a review from an older HEAD.

## Phase 7 — MERGE_READY

```powershell
pwsh -NoProfile -File scripts/agent/merge-ready.ps1 -PrNumber <N>
```

Only when ready, present:

- PR number/title/URL
- exact `headSha`
- `Quality` / `Test` status
- final AI review P0/P1/P2 = 0
- remaining P3, if any

Then ask:

```text
この HEAD (<sha>) を main に squash merge してよいですか？
```

Do not invoke `merge-task.ps1` until the user explicitly approves that exact SHA.

## BLOCKED conditions

Return BLOCKED for:

- pre-existing/stale guarded task state
- dirty worktree
- GitHub host preflight failure
- baseline main CI failure
- missing/incorrect repository protection
- materially ambiguous requirements
- required dependency addition awaiting approval
- exhausted local/CI/PR-review repair bounds
- branch/PR/HEAD identity mismatch
- security-sensitive decision requiring a human
