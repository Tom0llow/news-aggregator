---
name: implement-feature
description: Implement a new feature or intentional behavior change in this repository. Use for requests such as "add", "implement", "support", or "introduce" functionality; do not use for bug-only fixes or read-only code review.
---

# Implement Feature

Implement the requested feature as the smallest coherent change that satisfies the requirement and preserves repository architecture.

Do not create commits, push branches, merge, or open pull requests unless the user explicitly asks.

## 1. Read repository instructions

Before editing:

1. Read the applicable `AGENTS.md`.
2. Read `ARCHITECTURE.md` if present.
3. Read:
   - `docs/rules/coding-style.md`
   - `docs/rules/testing.md`
   - `docs/rules/architecture.md`
4. If the change affects architecture, search `docs/decisions/` for relevant ADRs.
5. Inspect `git status --short --branch` and preserve existing user changes.

A deeper `AGENTS.md` overrides broader instructions within its scope.

## 2. Understand the requested behavior

Identify:

- expected user-visible or API behavior,
- inputs and outputs,
- success criteria,
- important edge cases,
- compatibility constraints,
- affected modules and callers.

If details are missing, infer the smallest behavior consistent with existing code and conventions.
Do not expand scope speculatively.

## 3. Inspect before designing

Search the repository for:

- similar features,
- existing abstractions,
- relevant ports/adapters,
- configuration patterns,
- tests covering nearby behavior,
- public APIs that may be affected.

Prefer extending an existing coherent pattern over introducing a new one.

Do not add a new abstraction solely because it might be useful later.

## 4. Check architectural impact

Before adding modules, dependencies, or interfaces, determine the correct layer.

Default dependency direction:

```text
interfaces
    ↓
application
    ↓
domain

infrastructure
    ↓
application / domain ports
```

Rules:

- keep business logic out of interfaces and infrastructure,
- do not introduce framework/vendor types into the domain,
- create ports only when dependency inversion or test isolation materially benefits the design,
- keep configuration and I/O at boundaries.

If the feature requires a long-lived architectural decision, create or propose an ADR according to `docs/decisions/README.md`.

## 5. Plan the smallest coherent change

Before editing, define a short implementation plan containing:

1. files/modules to modify,
2. behavioral change,
3. tests to add/update,
4. validation commands.

Keep the plan proportional to the task.

For small changes, 2-4 steps are enough.

## 6. Implement

During implementation:

- keep the diff scoped to the feature,
- preserve existing naming and style,
- prefer explicit types,
- reuse project-owned abstractions,
- avoid unrelated refactors,
- avoid new dependencies unless necessary,
- update all callers when changing a public contract,
- keep backward compatibility unless breaking behavior is explicitly requested.

When adding a dependency:

1. confirm existing dependencies/stdlib are insufficient,
2. update `pyproject.toml`,
3. update `uv.lock`,
4. validate the full relevant test suite.

## 7. Add or update tests

Behavior changes require tests unless testing is genuinely impractical.

Cover at minimum:

- main success path,
- important boundary condition,
- meaningful failure behavior.

Prefer unit tests for domain/application behavior and integration tests for infrastructure boundaries.

Do not test implementation details when observable behavior is sufficient.

## 8. Validate incrementally

Run the narrowest useful checks first.

Typical order:

```bash
uv run pytest <relevant-test-path> -q
uv run ruff check <changed-paths>
uv run mypy <changed-paths>
```

Then run repository-level checks when configured:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

If the repository uses different commands, follow repository configuration instead of inventing new tooling.

Do not hide failures by weakening tests, adding unjustified ignores, or suppressing type errors.

## 9. Review the diff

Before completion:

```bash
git status --short
git diff --check
git diff
```

Check that:

- every changed file is relevant,
- no user changes were overwritten,
- no generated junk or secrets were introduced,
- no debug output remains,
- documentation changed when public behavior/setup changed,
- accepted ADRs are not contradicted.

## 10. Completion report

Report concisely:

- what changed,
- important design choices,
- tests/checks run,
- any unresolved risk or limitation.

Do not claim checks passed unless they were actually run successfully.
