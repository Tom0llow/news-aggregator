# AGENTS.md

> This template assumes Python + uv + Ruff + mypy + pytest.
> If this repository uses different tools, update the commands below first.

## 1. Purpose

This file defines the default working contract for AI coding agents in this repository.
Keep this file concise. Detailed rules live under `docs/rules/`.

Project-specific facts that change frequently should be documented in the appropriate project docs instead of accumulating here.

## 2. Repository map

Typical layout:

```text
.
├─ AGENTS.md
├─ src/                  # application code
├─ tests/                # automated tests
├─ docs/
│  └─ rules/
│     ├─ coding-style.md
│     ├─ git-workflow.md
│     └─ testing.md
├─ .codex/
│  └─ rules/
│     └─ default.rules
└─ pyproject.toml
```

Before making changes, read the rules relevant to the task:

- Code changes: `docs/rules/coding-style.md`
- Architecture / module placement: `ARCHITECTURE.md` and `docs/rules/architecture.md`
- Git / branch / commit work: `docs/rules/git-workflow.md`
- Test changes or bug fixes: `docs/rules/testing.md`

Before making significant architectural changes:

1. Read `ARCHITECTURE.md`.
2. Read `docs/rules/architecture.md`.
3. Search `docs/decisions/` for relevant ADRs.
4. Create a new ADR when the decision has meaningful long-term architectural impact.
5. Never silently contradict an Accepted ADR.
6. When replacing a decision, create a new ADR and mark the previous ADR as Superseded.

If a deeper directory contains another `AGENTS.md`, follow that file for work inside its scope.

## 3. Default workflow

For every implementation task:

1. Inspect the existing code and tests before editing.
2. Identify the smallest set of files required for the task.
3. Preserve existing architecture and conventions unless the task explicitly changes them.
4. Implement the smallest coherent change.
5. Add or update tests when behavior changes.
6. Run focused validation first, then the repository-level checks required below.
7. Review `git diff` and remove unrelated changes.
8. Summarize what changed, validation performed, and any remaining risks.

Do not stop after writing code when validation can be run locally.

## 4. Required commands

### Install / sync

```bash
uv sync
```

### Format

```bash
uv run ruff format .
```

### Lint

```bash
uv run ruff check .
```

### Type check

```bash
uv run mypy src tests
```

### Test

```bash
uv run pytest
```

### Recommended final validation

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

If a command is not configured in this repository, do not invent configuration silently. Report the mismatch and use the closest existing project command.

## 5. Implementation rules

- Prefer existing abstractions, naming, and patterns over introducing new ones.
- Keep changes local to the requested task.
- Do not perform opportunistic refactors unless they are required for correctness.
- Do not add a dependency when the standard library or an existing dependency is sufficient.
- Do not change public APIs without updating callers and tests.
- Do not weaken typing merely to silence type-checker errors.
- Do not catch broad exceptions unless the boundary genuinely requires it.
- Do not suppress lint/type errors without a short, specific justification.
- Keep I/O and external side effects near application boundaries.
- Prefer deterministic behavior and explicit dependencies.
- Preserve backwards compatibility unless the task explicitly permits a breaking change.

## 6. Testing rules

Behavioral changes require tests unless testing is technically impossible or disproportionate.

For bug fixes:

1. Add or identify a test that reproduces the bug.
2. Implement the fix.
3. Confirm the regression test passes.

Never delete, skip, or relax a failing test only to make CI pass unless the test itself is proven incorrect.

See `docs/rules/testing.md` for details.

## 7. Git safety

Before editing, inspect the working tree:

```bash
git status --short --branch
```

Rules:

- Never discard user changes.
- Never overwrite files unrelated to the task.
- Never use `git reset --hard`.
- Never use `git clean -fd` / `git clean -fdx`.
- Never force-push.
- Never rewrite published history unless explicitly instructed.
- Do not amend an existing commit unless explicitly instructed.
- Outside the `autonomous-task` workflow, do not push, merge, or open a PR unless the user explicitly asks for it.
- The `autonomous-task` workflow may autonomously create its guarded branch, commit, push, and PR, but it must stop at `MERGE_READY`.
- Final merge always requires explicit user approval of the exact reviewed HEAD SHA.
- Do not commit unrelated changes.

Local branch and commit operations must follow `docs/rules/git-workflow.md`.

## 8. Dependencies and configuration

Before adding or upgrading a dependency:

1. Check whether the repository already provides an equivalent capability.
2. Prefer the smallest dependency that solves the actual requirement.
3. Update lock files together with dependency declarations.
4. Run tests after dependency changes.
5. Mention the dependency change in the final summary.

Never commit secrets, credentials, tokens, private keys, or `.env` contents.

## 9. Documentation

Update documentation when a change affects:

- public behavior,
- user-facing configuration,
- commands or setup,
- architecture or module responsibilities,
- external API contracts.

Do not create documentation that merely repeats obvious code.

## 10. Definition of Done

A task is complete when all applicable items are true:

- Requested behavior is implemented.
- Relevant tests are added or updated.
- Focused tests pass.
- Ruff checks pass.
- Type checks pass when configured.
- Full relevant test suite passes.
- `git diff` contains no accidental changes.
- No secrets or generated junk files were introduced.
- Documentation is updated when behavior or setup changed.
- Final response clearly states validation performed and any unresolved issue.

## 11. Guarded Git operations

For autonomous task Git/GitHub mutations, do not invoke raw mutation commands.

Use only:

```powershell
pwsh -NoProfile -File scripts/agent/start-task.ps1 ...
pwsh -NoProfile -File scripts/agent/commit-task.ps1 ...
pwsh -NoProfile -File scripts/agent/push-task.ps1
pwsh -NoProfile -File scripts/agent/create-pr.ps1 ...
```

The autonomous workflow must stop at `MERGE_READY`.

Only after explicit user approval may the coordinator invoke:

```powershell
pwsh -NoProfile -File scripts/agent/merge-task.ps1 `
  -PrNumber <number> `
  -ExpectedHeadSha <reviewed-sha>
```

Never bypass the wrappers with raw:

```text
git add
git commit
git switch / checkout
git push
git merge / rebase / cherry-pick
gh pr create
gh pr merge
```

Read-only Git inspection such as `git status`, `git diff`, `git log`, and `git show`
remains allowed according to repository policy.

## 12. Autonomous development workflow

For any non-trivial request that modifies repository code, MUST use the
`autonomous-task` workflow unless the user explicitly requests local-only work or read-only analysis.

Expected lifecycle:

```text
requirement
→ guarded agent/* branch
→ implementer
→ independent reviewer
→ bounded fixes
→ Ruff / mypy / pytest
→ guarded commit
→ guarded push
→ PR
→ CI / bounded CI fixes
→ final independent PR review / bounded fixes
→ MERGE_READY
→ explicit human merge approval
→ guarded squash merge
```

### Git/GitHub mutations

Codex must not use raw mutation commands.

Use only:

```powershell
pwsh -NoProfile -File scripts/agent/start-task.ps1 ...
pwsh -NoProfile -File scripts/agent/commit-task.ps1 ...
pwsh -NoProfile -File scripts/agent/push-task.ps1
pwsh -NoProfile -File scripts/agent/create-pr.ps1 ...
pwsh -NoProfile -File scripts/agent/wait-ci.ps1 ...
pwsh -NoProfile -File scripts/agent/merge-ready.ps1 ...
```

The workflow must stop at `MERGE_READY`.

Only after the user explicitly approves the exact HEAD SHA that was presented
as MERGE_READY may Codex invoke:

```powershell
pwsh -NoProfile -File scripts/agent/merge-task.ps1 `
  -PrNumber <number> `
  -ExpectedHeadSha <approved-sha>
```

Never bypass the wrappers with raw branch/commit/push/PR/merge mutation commands.

### Human interaction target

Normal successful task:

1. user provides the requirement;
2. user approves or rejects the exact merge-ready HEAD.

Additional user interaction is allowed only for genuine blockers such as
ambiguous product requirements, missing GitHub setup, required dependency
approval, or an exhausted bounded repair loop.
