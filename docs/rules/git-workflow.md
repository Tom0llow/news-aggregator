# Git Workflow

## 1. Strategy

`main` is the permanent integration branch.

Normal changes use short-lived branches and Pull Requests.

There are two execution modes:

1. **manual/human workflow**
2. **guarded autonomous Codex workflow**

Rules for one mode must not be applied to the other in a way that creates
contradictions.

## 2. Branch naming

Manual branches may use:

```text
feat/<topic>
fix/<topic>
refactor/<topic>
test/<topic>
docs/<topic>
chore/<topic>
```

Guarded autonomous branches use only:

```text
agent/<generated-task-name>-<timestamp>
```

Codex must create autonomous branches only through:

```powershell
pwsh -NoProfile -File scripts/agent/start-task.ps1 -TaskName "<task>"
```

## 3. Before starting work

Inspect:

```bash
git status --short --branch
git log -5 --oneline
```

Never discard pre-existing user work.

The autonomous workflow requires a clean worktree, local `main`, and no existing
guarded task state before creating a task branch.

## 4. Commit format

Use Conventional Commits:

```text
<type>(<optional-scope>): <description>
```

Common types:

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

## 5. Commit scope

One commit should represent one coherent logical change.

Do not mix unrelated refactors, formatting, dependency upgrades, or generated
content.

## 6. Commit policy

Outside `autonomous-task`, do not create commits unless the user asks or the
surrounding workflow explicitly expects them.

Inside `autonomous-task`, the coordinator is authorized to commit through:

```powershell
pwsh -NoProfile -File scripts/agent/commit-task.ps1 -Message "<message>"
```

The implementation/reviewer/fixer subagents themselves never commit.

Do not amend or rewrite published history in the autonomous workflow.

## 7. Remote operations

Outside `autonomous-task`, push/PR/merge actions require explicit user intent.

Inside `autonomous-task`, these are authorized without another user turn:

```text
guarded agent/* branch creation
guarded commit
guarded push
guarded PR creation
CI polling / read-only PR inspection
```

Use only the wrappers in `scripts/agent/`.

The autonomous workflow must stop at `MERGE_READY`.

Final merge requires explicit user approval of the exact reviewed HEAD SHA and
then uses `merge-task.ps1`.

## 8. Force push

Codex must never force-push in the autonomous workflow.

`main` must reject force pushes.

Manual history repair is an exceptional human operation and is outside the
autonomous contract.

## 9. Pull Requests

Each PR must have one clear purpose.

Before publication:

- validation passes
- diff is scoped
- no secrets/debug junk
- documentation is updated when needed

PR body:

```text
## Summary

## Validation

## Architecture / ADR

## Risks / Notes
```

## 10. CI

Required checks are:

```text
Quality
Test
```

The workflow must not declare CI successful until both required check names
exist and all checks are passing/skipping.

Known baseline CI failures are fixed before unrelated autonomous work begins.

## 11. Merge policy

Repository policy is squash-only.

`main` requires:

- Pull Request association
- 0 mandatory GitHub human approvals
- `Quality` and `Test`
- strict/up-to-date status checks
- linear history
- resolved conversations
- no force push
- no deletion

The human safety boundary is the explicit approval of the exact MERGE_READY
HEAD, not an additional GitHub Approve click.

## 12. Parallelism

Writable agents are serialized in the current worktree.

Do not start a second guarded autonomous task while
`.git/codex-task.json` represents an active task.

Read-only reviewer/analysis agents may run concurrently when safe.

## 13. Dependencies

Dependency additions/removals are an explicit approval boundary.

When approved, update `pyproject.toml` and `uv.lock` together and rerun the full
validation suite.

## 14. Final review

Before publication/merge, inspect:

```bash
git status --short
git diff --check
git diff
```

Do not claim validation or review passed unless it actually ran on the current
HEAD.
