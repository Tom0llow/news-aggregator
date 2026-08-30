---
name: fix-bug
description: Diagnose and fix an incorrect existing behavior or regression. Use for bugs, exceptions, failing cases, regressions, and "this should work but does not"; do not use for feature additions or read-only review.
---

# Fix Bug

Fix the bug by reproducing it, identifying the root cause, adding regression coverage, and applying the smallest correct change.

Do not create commits, push branches, merge, or open pull requests unless the user explicitly asks.

## 1. Read repository instructions

Before editing:

1. Read the applicable `AGENTS.md`.
2. Read:
   - `docs/rules/coding-style.md`
   - `docs/rules/testing.md`
   - `docs/rules/architecture.md`
3. Read `ARCHITECTURE.md` when the affected boundary is non-trivial.
4. Search relevant ADRs when the bug touches an architectural decision.
5. Inspect `git status --short --branch` and preserve user changes.

## 2. Establish the failure

Gather evidence before changing code.

Use, in order of preference:

1. an existing failing test,
2. a minimal new regression test,
3. a minimal reproducible command/input,
4. logs or traceback supported by the affected code path.

Identify:

- expected behavior,
- actual behavior,
- triggering inputs/state,
- first incorrect state transition or result.

Do not begin by broadly refactoring suspicious code.

## 3. Trace the root cause

Inspect:

- failing call path,
- nearby tests,
- recent assumptions,
- boundary conversions,
- error handling,
- state mutation,
- type/nullability behavior,
- affected callers.

Distinguish root cause from symptoms.

Examples:

```text
Symptom: HTTP 500
Root cause: repository returns None that application assumes is an entity
```

```text
Symptom: wrong total
Root cause: domain calculation mutates shared input collection
```

Do not add retries, exception swallowing, default values, or guards merely to hide the symptom unless that is the correct contract.

## 4. Add a regression test

Whenever practical, create a test that:

1. fails before the fix,
2. represents the real bug,
3. passes after the fix,
4. would fail again if the bug returned.

Name the test after the behavior.

Prefer:

```python
def test_parse_order_rejects_negative_quantity():
    ...
```

Avoid tests that only assert a private implementation detail.

If an existing test already reproduces the bug, do not duplicate it unnecessarily.

## 5. Apply the smallest correct fix

Fix the root cause with the narrowest coherent change.

Rules:

- do not broaden scope,
- avoid unrelated refactoring,
- preserve public behavior outside the bug,
- preserve architecture boundaries,
- do not weaken validation unless the prior validation is proven wrong,
- do not add broad `except Exception`,
- do not convert errors to `None` merely to silence failures,
- do not add `# type: ignore` unless specifically justified.

If the correct fix requires an architectural change, follow the ADR process rather than silently introducing a new pattern.

## 6. Check adjacent cases

After the direct regression passes, inspect closely related cases:

- empty/missing input,
- minimum/maximum values,
- repeated calls,
- duplicate data,
- error paths,
- boundary conversions,
- concurrency/state issues when relevant.

Do not turn this into an exhaustive unrelated test campaign.

## 7. Validate

Run the regression test first:

```bash
uv run pytest <regression-test> -q
```

Then relevant tests:

```bash
uv run pytest <affected-test-area> -q
```

Then configured repository checks:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

If a failure is unrelated and pre-existing, verify that with evidence and report it clearly.

Never:

- delete the failing test,
- add unjustified `skip` or `xfail`,
- weaken assertions just to make CI green,
- increase timeouts without understanding why.

## 8. Review the diff

Before completion:

```bash
git status --short
git diff --check
git diff
```

Verify:

- regression coverage is present,
- fix addresses root cause,
- diff contains no accidental edits,
- no user changes were overwritten,
- architecture remains consistent.

## 9. Completion report

Report:

- observed failure/root cause,
- fix applied,
- regression test added or reused,
- validation commands run,
- any remaining risk.

Keep root-cause explanation concrete and evidence-based.
