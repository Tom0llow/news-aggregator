# Testing

## 1. Principles

Tests should provide fast, deterministic evidence that behavior is correct.

Prefer many focused unit tests, fewer integration tests, and only necessary end-to-end tests.

## 2. Default framework

Use `pytest` unless the repository explicitly uses another framework.

```bash
uv run pytest
```

Focused test:

```bash
uv run pytest tests/path/to/test_module.py -q
```

Single test:

```bash
uv run pytest tests/path/to/test_module.py::test_case_name -q
```

## 3. Test layers

### Unit tests

Use for domain rules, pure functions, parsing, validation, state transitions, and edge cases.

Unit tests should not require real network services, production databases, or external credentials.

### Integration tests

Use for:

* database repositories,
* HTTP boundaries,
* filesystem integration,
* serialization contracts,
* framework wiring.

### End-to-end tests

Use only for critical user-visible flows that cannot be adequately covered at lower layers.

## 4. Behavior changes

For a new feature, cover the main success path, important boundaries, and meaningful failures.

For a bug fix:

1. write or identify a regression test,
2. implement the fix,
3. confirm the test passes,
4. run related tests.

## 5. Test naming

Prefer:

```python
def test_parse_order_rejects_negative_quantity():
    ...


def test_expired_token_returns_unauthorized():
    ...
```

Avoid:

```python
def test_parser_1():
    ...


def test_error():
    ...
```

## 6. Test structure

Prefer Arrange / Act / Assert when it improves readability.

```python
def test_discount_is_applied_for_premium_customer():
    customer = Customer(plan="premium")
    order = Order(total=1000)

    result = calculate_total(customer, order)

    assert result == 900
```

## 7. Assertions

Assert observable behavior, not internal implementation details.

```python
assert result.status == Status.SUCCESS
assert result.total == 42
```

## 8. Fixtures

Fixtures should be small, composable, explicit, and narrowly scoped.

Avoid giant autouse fixtures that hide important setup.

## 9. Mocking

Mock system boundaries, not internal implementation details.

Good targets include HTTP clients, time, randomness, email providers, and external service adapters.

## 10. Time and randomness

Tests must be deterministic.

* inject or freeze time when needed,
* seed randomness when needed,
* avoid sleep-based synchronization,
* avoid depending on execution order.

## 11. Filesystem tests

Use pytest facilities such as `tmp_path`.

Do not leave test artifacts in the repository.

## 12. Database tests

* Never use production databases.
* Reset or roll back state.
* Avoid ordering dependencies.
* Test migrations when schema changes.

## 13. Network tests

Unit tests must not require arbitrary public network access.

Mock APIs at adapter boundaries. Use explicit integration tests where real-service testing is required.

## 14. Edge cases

Where relevant, test:

* empty input,
* missing values,
* min/max boundaries,
* malformed input,
* duplicates,
* timeout/error responses,
* partial failure,
* permission errors.

## 15. Parametrization

Use `pytest.mark.parametrize` for multiple cases exercising the same behavior.

```python
import pytest


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "zero"),
        (1, "positive"),
        (-1, "negative"),
    ],
)
def test_classify_number(value: int, expected: str):
    assert classify_number(value) == expected
```

## 16. Slow tests

Mark slow or special-environment tests explicitly when supported.

```python
@pytest.mark.integration
def test_database_round_trip():
    ...
```

## 17. Coverage

Coverage is a diagnostic, not the goal.

Do not add meaningless assertions solely to increase coverage.

Do not lower configured coverage thresholds merely to make a change pass.

## 18. Agent validation workflow

Codex should validate incrementally:

1. nearest relevant tests,
2. relevant test package,
3. lint/type checks,
4. full required suite.

Example:

```bash
uv run pytest tests/domain/test_pricing.py -q
uv run ruff check src/domain tests/domain
uv run mypy src/domain tests/domain
uv run pytest
```

## 19. Never hide failures

Do not make tests pass by:

* deleting failing tests,
* adding unjustified `skip` / `xfail`,
* weakening assertions,
* swallowing unexpected exceptions,
* increasing timeouts without understanding the cause.

## 20. Test review checklist

Before completion, check:

* Does the test describe behavior?
* Would it fail if the bug returned?
* Is it deterministic?
* Is setup understandable?
* Is implementation coupling minimal?
* Is external state cleaned up?
* Are important errors covered?
