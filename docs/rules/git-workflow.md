# Git Workflow

## 1. Strategy

Use a lightweight GitHub Flow / trunk-based workflow.

`main` is the only permanent integration branch unless the repository explicitly documents otherwise.

Changes should be developed on short-lived branches and merged through Pull Requests.

## 2. Branch naming

Use:

```text
feat/<issue-or-topic>
fix/<issue-or-topic>
refactor/<topic>
test/<topic>
docs/<topic>
chore/<topic>
```

Examples:

```text
feat/123-user-auth
fix/231-timeout-handling
refactor/prediction-service
docs/local-setup
```

Keep names short and descriptive.

## 3. Before starting work

Inspect repository state:

```bash
git status --short --branch
git log -5 --oneline
```

If the working tree already contains changes:

- assume they may belong to the user,
- do not discard them,
- do not include them in the task unless relevant,
- mention conflicts if they prevent safe progress.

## 4. Commit format

Use Conventional Commits:

```text
<type>(<optional-scope>): <description>
```

Allowed common types:

```text
feat
fix
refactor
test
docs
perf
build
ci
chore
```

Examples:

```text
feat(api): add customer lookup endpoint
fix(parser): handle empty input
refactor(domain): extract pricing policy
test(auth): cover expired token case
docs: document local setup
```

Use imperative, concise descriptions.

## 5. Commit scope

One commit should represent one coherent logical change.

Do not mix unrelated concerns such as:

- feature implementation,
- unrelated refactoring,
- mass formatting,
- dependency upgrades,
- generated files.

A commit should be understandable and revertible on its own whenever practical.

## 6. Agent commit policy

Codex may edit files and run validation as part of normal task execution.

Do not create commits unless:

- the user explicitly asks for commits, or
- the surrounding workflow explicitly states that local commits are expected.

When creating a commit:

1. inspect `git diff`,
2. stage only task-related files/hunks,
3. verify `git diff --cached`,
4. use a Conventional Commit message,
5. do not amend existing commits unless explicitly instructed.

Never commit secrets or local environment files.

## 7. Remote operations

Do not perform these operations unless the user explicitly asks:

```text
git push
gh pr create
gh pr merge
git merge
git rebase against a shared branch
```

Never force-push unless the user explicitly requests it and the repository policy permits it.

Prefer:

```bash
git push --force-with-lease
```

over `git push --force` when rewriting a non-shared feature branch is intentionally required.

## 8. Prohibited destructive operations

Do not run:

```bash
git reset --hard
git clean -fd
git clean -fdx
git checkout -- .
```

without explicit user instruction and a clear understanding of what will be lost.

Do not rewrite published/shared history by default.

## 9. Pull Requests

Each PR should have one clear purpose.

Before opening a PR:

- sync with the current target branch if necessary,
- run required validation,
- remove debug code,
- review the final diff,
- ensure documentation is updated when needed.

Recommended PR content:

```text
## Summary
- What changed
- Why it changed

## Validation
- Commands/tests run

## Risks / Notes
- Migration, compatibility, rollout, or known limitations
```

## 10. Merge policy

Default recommendation: **Squash Merge** into `main`.

Benefits:

- keeps `main` history concise,
- allows iterative WIP commits on feature branches,
- produces one logical revert unit per PR.

Use another merge strategy only when the repository explicitly requires it.

## 11. Keeping branches current

For a private short-lived branch, prefer rebase when the team policy permits:

```bash
git fetch origin
git rebase origin/main
```

For shared branches, avoid rewriting collaborators' history. Prefer merge or coordinate before rebasing.

Never resolve conflicts by blindly choosing `ours` or `theirs`. Understand each conflict.

## 12. Parallel Codex / agent work

When multiple agents work concurrently, isolate each task with a separate branch and preferably a separate Git worktree.

Example:

```bash
git fetch origin
git worktree add ../worktrees/feature-a -b feat/feature-a origin/main
git worktree add ../worktrees/fix-b -b fix/fix-b origin/main
```

Rules:

- one task per branch/worktree,
- do not let multiple agents edit the same worktree concurrently,
- integrate only after each branch passes its own validation,
- resolve conflicts deliberately in the integration branch/worktree.

Remove finished worktrees after integration:

```bash
git worktree remove ../worktrees/feature-a
```

## 13. Generated files and lock files

Commit generated files only when repository policy requires them.

When dependencies change, update and commit the corresponding lock file in the same logical change.

Do not manually edit generated lock files unless the toolchain explicitly requires it.

## 14. Final Git review

Before declaring the task complete:

```bash
git status --short
git diff --check
git diff
```

If commits were created, also inspect:

```bash
git log --oneline --decorate -5
```

Confirm that no unrelated files or accidental formatting changes are present.
