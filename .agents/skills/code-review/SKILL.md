---
name: code-review
description: Perform a read-only, defect-first review of code changes. Use when asked to review a diff, branch, commit, pull request, or implementation; do not edit files or implement fixes unless separately requested.
---

# Code Review

Perform a read-only review focused on concrete defects, regressions, architectural violations, security issues, and missing tests.

Do not modify files.
Do not create commits.
Do not push.
Do not post remote review comments.
Do not fix findings unless the user separately asks for implementation.

## 1. Read repository instructions

Before reviewing:

1. Read the applicable `AGENTS.md`.
2. Read:
   - `docs/rules/coding-style.md`
   - `docs/rules/testing.md`
   - `docs/rules/architecture.md`
3. Read `ARCHITECTURE.md` for structural changes.
4. Search relevant ADRs when the change affects architecture or a prior design decision.

Treat repository rules as review criteria.

## 2. Determine the review target

Use the target explicitly requested by the user.

Examples:

- uncommitted working-tree changes,
- staged changes,
- one commit,
- commit range,
- feature branch versus base branch,
- pull-request-equivalent diff.

For a branch review, prefer the changes that would actually merge:

```bash
git merge-base <base> HEAD
git diff <merge-base>...HEAD
```

Do not assume `git diff <base> HEAD` is equivalent when branches have diverged.

Preserve the working tree; review commands should be read-only.

## 3. Inspect the complete diff

Read the whole relevant diff, not just the first suspicious file.

For each changed area, inspect enough surrounding code to understand:

- existing contracts,
- callers,
- state/data flow,
- error behavior,
- test coverage,
- architecture boundaries.

Continue reviewing after finding the first defect.

## 4. Review priorities

Prioritize actionable issues in this order:

### Correctness

Look for:

- wrong outputs,
- missing cases,
- invalid assumptions,
- off-by-one/boundary errors,
- mutation/state bugs,
- error handling that changes semantics,
- backward-incompatible behavior.

### Data and state integrity

Look for:

- partial updates,
- inconsistent transaction behavior,
- race-prone state changes,
- duplicate processing,
- non-idempotent retry behavior where retries are expected.

### Security and privacy

Look for:

- secret leakage,
- unsafe command construction,
- SQL injection,
- authorization bypass,
- insecure deserialization,
- sensitive logging,
- unsafe external input handling.

### Architecture

Look for:

- outward domain dependencies,
- business rules in infrastructure/interfaces,
- vendor/framework types leaking inward,
- duplicated abstractions,
- contradictions with Accepted ADRs.

### Reliability and performance

Flag only meaningful issues:

- unbounded loops/queries/tasks,
- obvious N+1 behavior,
- blocking I/O in async paths,
- uncontrolled retry storms,
- large avoidable memory materialization.

Do not report speculative micro-optimizations.

### Tests

Check whether behavior changes have effective coverage.

Look for:

- missing regression cases,
- assertions that do not exercise the change,
- tests coupled only to implementation details,
- removed/weakened coverage,
- nondeterministic tests.

## 5. Validate each finding

Before reporting a finding:

1. trace the affected code path,
2. confirm the changed code introduced or exposes the issue,
3. inspect relevant callers/tests,
4. distinguish definite defect from preference.

Do not report style preferences already enforced by Ruff/formatter unless they reveal a semantic issue.

Do not invent failure scenarios unsupported by the code.

## 6. Severity

Use these levels:

### P0 — Critical

Immediate severe impact, such as:

- data loss/corruption at broad scale,
- critical security compromise,
- system-wide outage caused by the change.

### P1 — High

Likely serious production defect requiring prompt correction.

Examples:

- common path crashes,
- authorization bypass,
- incorrect persistent state,
- major backward incompatibility.

### P2 — Medium

Real defect with narrower impact or workaround.

Examples:

- edge case produces incorrect result,
- important missing validation,
- resource leak under a specific path.

### P3 — Low

Actionable but limited issue.

Examples:

- misleading error behavior,
- maintainability problem likely to cause a defect,
- missing targeted test for a meaningful edge case.

Do not use severity labels to inflate subjective preferences.

## 7. Finding format

For each finding include:

```text
[P1/P2/P3] Short imperative title

Location: path/to/file.py:line-range

Why:
Explain the concrete failure or risk.

Trigger:
Describe the input/state/path needed to expose it.

Suggested direction:
Briefly describe how the author can fix it without writing the patch.
```

Keep locations as narrow as possible.

If the environment provides exact diff line numbers, use them.

## 8. Review result

Order findings by severity, then by file/path.

If no actionable defects are found, say so explicitly and mention any remaining testing uncertainty.

A good final structure is:

```text
Findings
1. [P1] ...
2. [P2] ...

Validation / scope
- Reviewed ...
- Checked ...
- Tests not run / tests run ...

Overall
Short assessment of merge risk.
```

Do not bury findings inside a long summary.

## 9. Optional validation

When safe and useful, run read-only validation such as:

```bash
uv run pytest <relevant-tests> -q
uv run ruff check .
uv run mypy src tests
```

Do not modify code to make review checks pass.

If tests cannot be run, state that limitation instead of assuming they pass.
