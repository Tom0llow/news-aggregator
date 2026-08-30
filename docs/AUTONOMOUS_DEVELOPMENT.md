# Autonomous Development Workflow

## Goal

Normal successful operation should require human interaction only twice:

```text
1. Human: "Implement X"
2. Human: "Merge the reviewed HEAD"
```

Everything between those points is bounded, auditable automation.

## Runtime lifecycle

```text
Requirement
  ↓
guarded `agent/*` branch
  ↓
Implementer
  ↓
Independent local Reviewer
  ↓
Fixer (only validated P0/P1/P2, max 2)
  ↓
Local validation
  ↓
guarded commit + push + PR
  ↓
GitHub CI
  ├─ fail → CI Analyst → Fixer → commit/push (max 2)
  └─ pass
  ↓
Independent final PR Reviewer
  ├─ P0/P1/P2 → Fixer → commit/push → CI → fresh review (max 2)
  └─ clean
  ↓
MERGE_READY exact HEAD
  ↓
HUMAN APPROVAL
  ↓
guarded squash merge with exact-HEAD match
```

## Why the merge remains human-controlled

Branch creation, commits, pushes, and PR creation are reversible or isolated to
`agent/*` branches.

Merging changes `main`, so it is the explicit human gate.

`merge-task.ps1` requires the exact SHA presented as MERGE_READY. If another
commit appears after approval, the merge is refused.

## One-time machine setup

```powershell
gh auth login
```

Install Git, GitHub CLI, PowerShell, Python/uv, and VS Code/Codex.

Project-local `.codex/` is applied only for a trusted project.

## One-time repository setup

First make sure the CI workflow has run at least once, then configure protection:

```powershell
pwsh -NoProfile -File scripts/github/configure-main-protection.ps1
```

This is an administrative operation and should require explicit approval.

Verify:

```powershell
pwsh -NoProfile -File scripts/github/verify-main-protection.ps1
```

Expected policy:

- PR-based changes to `main`
- required `Quality` and `Test` checks
- strict/up-to-date required checks
- admins also subject to protection
- linear history
- force push disabled
- branch deletion disabled
- conversations resolved
- no mandatory GitHub human reviewer

The last point is intentional: human control is the final merge approval, not an
additional GitHub "Approve" click.

## Normal usage

Give Codex a concrete requirement, for example:

```text
顧客一覧をCSVエクスポートできるようにして。
UTF-8、ヘッダーあり、空データにも対応。
```

The project instructions should route this to `autonomous-task`.

When ready, Codex should return something like:

```text
MERGE_READY
PR: #42
URL: ...
HEAD: abc123...
CI: PASS
AI final review: P0/P1/P2 = 0

この HEAD (abc123...) を main に squash merge してよいですか？
```

Reply:

```text
mergeして
```

Codex must merge only that exact previously presented HEAD.

## When more than two human interactions are expected

Automation should stop early only for real blockers:

- dirty working tree that may contain user work
- missing GitHub auth or branch protection
- materially ambiguous acceptance criteria
- dependency addition requiring approval
- security/product decision
- repeated repair loops reaching their cap
- external CI outage
- PR identity/SHA mismatch

These are safety exits, not normal workflow steps.

## Bounded loops

Automatic repair loops are deliberately finite:

| Loop | Maximum fixer rounds |
| --- | ---: |
| Local code review | 2 |
| CI failure repair | 2 |
| Final PR review | 2 |

After the bound, return `BLOCKED` with remaining evidence.

## Security boundaries

Allowed autonomous mutations are only the guarded wrappers.

Raw commands such as these are blocked for Codex:

```text
git add
git commit
git switch
git push
git merge
git rebase
gh pr create
gh pr merge
gh api
```

This does not prevent a human from using Git normally in their own terminal.

## Current VS Code caveat

Codex subagent workflows are available in current IDE releases, but client
versions can differ in how the subagent lifecycle UI/tools are exposed.

The orchestration therefore depends on bounded role prompts and fresh subagent
contexts, not on recursive subagent spawning.
