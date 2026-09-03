# Coding Style

## 1. Goals

Optimize for:

1. correctness,
2. readability,
3. maintainability,
4. testability,
5. simplicity.

Prefer boring, explicit code over clever abstractions.

## 2. Formatting and linting

Formatting and mechanically enforceable style belong in tools, not prose.

Default tools:

- formatter: Ruff formatter
- linter: Ruff
- type checker: mypy

Do not manually fight the configured formatter.

Recommended commands:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src tests
```

Repository configuration in `pyproject.toml` is authoritative when it conflicts with examples in this document.

## 3. Python version

Use the Python version declared by the repository.

Do not introduce syntax requiring a newer Python version than the project supports.

## 4. Imports

- Use absolute imports for application modules unless the existing package clearly prefers otherwise.
- Avoid wildcard imports.
- Remove unused imports.
- Avoid import-time side effects.
- Do not modify `sys.path` from application code to make imports work.
- Resolve circular imports by fixing responsibilities rather than hiding them with local imports, unless a local import is intentionally justified.

## 5. Naming

Use conventional Python naming:

- modules / functions / variables: `snake_case`
- classes / exceptions: `PascalCase`
- constants: `UPPER_SNAKE_CASE`
- private implementation details: leading `_`

Names should describe domain meaning, not implementation trivia.

Prefer:

```python
retry_count
prediction_result
load_customer
```

Avoid:

```python
x1
data2
helper
manager
util
```

unless the meaning is genuinely obvious from a narrow scope.

## 6. Functions

A function should have one clear responsibility.

Prefer:

- small interfaces,
- explicit inputs and outputs,
- early returns for guard clauses,
- pure functions for domain calculations,
- dependency injection for external effects when useful for testing.

Avoid:

- hidden global state,
- boolean flags that select unrelated behaviors,
- functions that both calculate data and perform unrelated I/O,
- deeply nested conditionals,
- premature generic frameworks.

If a function becomes difficult to name precisely, it probably has too many responsibilities.

## 7. Type hints

Type annotations are required for new or modified public functions and methods unless the project explicitly follows another policy.

Prefer precise types.

Good:

```python
from collections.abc import Sequence
from pathlib import Path


def load_records(path: Path) -> Sequence[Record]:
    ...
```

Avoid using `Any` merely to silence errors.

Use `Any` only at genuine dynamic boundaries and narrow the type as soon as practical.

Prefer modern type syntax when supported by the project's Python version:

```python
str | None
list[str]
dict[str, int]
```

## 8. Data models

Use the lightest construct that expresses the requirement.

Typical preference:

1. simple immutable value → primitive / tuple / `NamedTuple`
2. structured internal data → `dataclass`
3. validated external input/output → existing project validation framework

Do not introduce Pydantic, attrs, or another model framework solely for convenience if the project does not already use it.

## 9. Error handling

- Raise exceptions for exceptional conditions, not normal branching.
- Catch the narrowest exception type possible.
- Preserve useful context when translating exceptions.
- Do not use bare `except:`.
- Do not silently swallow exceptions.
- Do not log and re-raise the same exception at every layer.

Prefer domain-specific exceptions when callers can meaningfully react to them.

Example:

```python
class CustomerNotFoundError(Exception):
    pass
```

When translating errors, chain them:

```python
try:
    ...
except ExternalApiError as exc:
    raise CustomerLookupError(customer_id) from exc
```

## 10. Logging

- Use the project's logging framework.
- Do not use `print()` for application logging.
- Log actionable context, not entire sensitive payloads.
- Never log secrets, access tokens, passwords, or private keys.
- Avoid duplicate logging of the same exception at multiple layers.

Prefer structured fields when the logging stack supports them.

## 11. I/O and side effects

Keep network, filesystem, database, subprocess, clock, and randomness boundaries explicit.

Domain logic should be testable without real external services whenever practical.

Prefer passing dependencies rather than importing globally instantiated clients deep in the domain layer.

## 12. Async code

Use async only when the surrounding architecture benefits from non-blocking I/O.

- Do not call blocking I/O directly from an async path when it can stall the event loop.
- Do not convert CPU-bound code to async merely because callers are async.
- Preserve cancellation behavior.
- Avoid unbounded task creation.

## 13. Collections and iteration

Prefer comprehensions when they remain readable.

Use a normal loop when:

- multiple steps are required,
- error handling is involved,
- side effects occur,
- the comprehension would be difficult to read.

Do not materialize large iterables unnecessarily.

## 14. Mutability

Prefer immutable inputs and return values when practical.

Do not mutate caller-owned collections unless the API explicitly promises mutation.

Avoid mutable default arguments.

Bad:

```python
def append_item(item: str, items: list[str] = []):
    ...
```

Good:

```python
def append_item(item: str, items: list[str] | None = None):
    values = [] if items is None else list(items)
    ...
```

## 15. Constants and configuration

- Do not scatter magic values across the codebase.
- Put stable domain constants near the domain they belong to.
- Put environment-specific values in configuration.
- Validate required configuration at startup or at the system boundary.
- Never hard-code credentials.

## 16. Comments and docstrings

Comments should explain **why**, not restate **what** the code does.

Every Python script must include a module docstring at the top of the file.
Place it immediately after any shebang and encoding declaration, and before
imports or executable statements.

Add docstrings for:

- public APIs,
- non-obvious domain behavior,
- constraints that cannot be expressed in types or tests.

Do not add verbose docstrings to trivial private helpers.

## 17. Architecture

Respect existing dependency direction.

As a default, prefer a structure similar to:

```text
presentation / interface
        ↓
application / use cases
        ↓
domain
        ↑
infrastructure adapters
```

Business rules should not depend directly on concrete database, HTTP, CLI, or framework implementations.

Do not introduce a new architectural layer for a single trivial use case.

## 18. Refactoring

Refactor when it directly supports the requested change or clearly reduces risk.

Avoid drive-by refactors.

When refactoring:

1. preserve behavior,
2. keep tests green,
3. separate mechanical changes from behavior changes when practical,
4. avoid renaming unrelated public symbols.

## 19. Security basics

Never:

- commit secrets,
- interpolate untrusted input into shell commands,
- disable TLS verification without an explicit requirement,
- deserialize untrusted arbitrary Python objects,
- construct SQL with string concatenation when parameterization is available.

Treat all external input as untrusted until validated.

## 20. Agent-specific rules

When generating code:

- Follow nearby code before inventing a new pattern.
- Search for existing helpers before creating duplicates.
- Do not replace a working implementation solely with a preferred personal style.
- Keep diffs minimal.
- Do not add TODOs instead of completing straightforward work.
- Do not leave dead code or commented-out implementations.
