---
name: autonomous-task
description: Run the full guarded coding lifecycle from a user requirement to MERGE_READY: branch, implementation, independent review/fix, commit, push, PR, CI remediation, final PR review, and readiness gate. Use for non-trivial implementation or bug-fix requests unless the user explicitly asks for local-only work.
---


# Autonomous Task Orchestrator

You are the coordinator for the repository's end-to-end autonomous development workflow.

The intended human interaction is:

```text
Human touch 1: requirement
AI: branch -> develop -> review/fix -> PR -> CI/fix -> PR review/fix -> MERGE_READY
Human touch 2: explicit merge approval
AI: guarded merge
```

Do not merge in this skill.

## Hard bounds

- writable agents run sequentially
- local review/fix: max 2 fixer rounds
- CI fix: max 2 fixer rounds per PR HEAD lineage
- final PR review fix: max 2 fixer rounds
- never recursively start another `autonomous-task`
- if a product/requirements decision is genuinely required, stop as BLOCKED instead of guessing

## Phase 0 — preflight

Run exactly one standalone guarded GitHub preflight command:

```powershell
pwsh -NoProfile -File scripts/agent/github-preflight.ps1
````

Rules:

* Do not run `gh auth status` directly.
* Do not diagnose GitHub authentication using sandboxed `gh`.
* Do not recommend `gh auth refresh` solely because sandboxed `gh`
  reports that the keyring token is invalid.
* Do not chain this wrapper with `&&`, `;`, or pipes.
* If this wrapper succeeds, treat GitHub authentication as valid.

## Phase 1 — guarded task branch

Start the task:

```powershell
pwsh -NoProfile -File scripts/agent/start-task.ps1 -TaskName "<short task name>"
```

The wrapper chooses a unique `agent/*` branch if none is supplied.

If the working tree is not clean, stop rather than risking user work.

## Phase 2 — implement + local independent review

Spawn `implementer` with:

- full requirement
- acceptance criteria
- architecture constraints
- instruction not to commit/push

After implementation, inspect the complete diff.

Spawn a fresh `reviewer` read-only.

Validate reviewer findings yourself.

For validated P0/P1/P2 findings, spawn `fixer`.
Repeat with a fresh reviewer, maximum two fixer rounds.

P3 findings may remain only if they do not affect acceptance criteria or merge safety; report them later.

## Phase 3 — repository validation

Run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Use repository-defined equivalents when these tools are not configured.

Do not publish known task-related failures.

## Phase 4 — commit / push / PR

Generate one coherent Conventional Commit subject and use:

```powershell
pwsh -NoProfile -File scripts/agent/commit-task.ps1 -Message "<type(scope): description>"
pwsh -NoProfile -File scripts/agent/push-task.ps1
```

Create a PR with a body containing:

- Summary
- Validation
- Architecture / ADR
- Risks / Notes

Use:

```powershell
pwsh -NoProfile -File scripts/agent/create-pr.ps1 -Title "<title>" -Body "<body>"
```

Capture PR number, URL, and HEAD SHA.

## Phase 5 — CI stabilization

Wait:

```powershell
pwsh -NoProfile -File scripts/agent/wait-ci.ps1 -PrNumber <N>
```

If CI fails, follow `.agents/skills/ci-fix/SKILL.md`.

After each pushed CI fix, wait for checks again.

Stop as BLOCKED if the CI fix bound is exhausted.

## Phase 6 — final PR review

Follow `.agents/skills/pr-review/SKILL.md`.

The final PR reviewer must inspect the complete current PR at the latest HEAD.

If fixes are pushed, CI must pass again before another final review.

Stop as BLOCKED if the PR review fix bound is exhausted with P0/P1/P2 remaining.

## Phase 7 — MERGE_READY gate

Run:

```powershell
pwsh -NoProfile -File scripts/agent/merge-ready.ps1 -PrNumber <N>
```

Only if it returns `ready = true`, report:

- PR number/title/URL
- exact `headSha`
- CI status
- review status
- remaining P3 findings, if any

Then ask exactly for the final decision:

```text
この HEAD (<sha>) を main に squash merge してよいですか？
```

Do not call `merge-task.ps1` in this turn unless the user has already explicitly approved that exact presented HEAD.

## BLOCKED conditions

Return BLOCKED instead of silently changing the contract when:

- working tree contains pre-existing changes
- GitHub auth/protection is missing
- requirements are materially ambiguous
- dependency addition needs approval and is required
- two local review fix rounds do not resolve P0/P1/P2
- two CI fix rounds fail
- two PR-review fix rounds leave P0/P1/P2
- branch/PR HEAD identity checks fail
- security-sensitive action requires a human decision

State the minimum action needed from the user.

