# ARCHITECTURE.md

> Replace placeholders such as `<package>` and `<project purpose>` with project-specific names.
> Keep this document focused on stable architectural decisions and system structure.
> Detailed implementation rules live in `docs/rules/architecture.md`.

# Architecture

## 1. Purpose

`<project-name>` is a Python application/library for:

> `<project purpose>`

The architecture is designed to optimize for:

1. correctness,
2. maintainability,
3. testability,
4. clear dependency boundaries,
5. incremental change by humans and coding agents.

The default architectural style is a lightweight layered architecture inspired by
Clean Architecture / Hexagonal Architecture, without introducing unnecessary abstractions.

---

## 2. High-level structure

Recommended repository layout:

```text
.
├─ src/
│  └─ <package>/
│     ├─ domain/
│     │  ├─ models.py
│     │  ├─ services.py
│     │  ├─ errors.py
│     │  └─ ports.py
│     │
│     ├─ application/
│     │  ├─ commands/
│     │  ├─ queries/
│     │  ├─ services.py
│     │  └─ dto.py
│     │
│     ├─ infrastructure/
│     │  ├─ persistence/
│     │  ├─ http/
│     │  ├─ external/
│     │  └─ config.py
│     │
│     ├─ interfaces/
│     │  ├─ api/
│     │  ├─ cli/
│     │  └─ jobs/
│     │
│     └─ bootstrap.py
│
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  └─ e2e/
│
├─ docs/
│  ├─ rules/
│  │  └─ architecture.md
│  └─ decisions/
│
├─ AGENTS.md
├─ ARCHITECTURE.md
└─ pyproject.toml
```

This is a guideline, not a requirement to create every directory in advance.
Create directories only when the project actually needs them.

---

## 3. Dependency direction

The core dependency rule is:

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

More explicitly:

```text
┌──────────────────────────────┐
│ Interfaces                   │
│ API / CLI / scheduled jobs   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Application                  │
│ Use cases / orchestration    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Domain                       │
│ Business rules / invariants  │
└──────────────────────────────┘

┌──────────────────────────────┐
│ Infrastructure               │
│ DB / HTTP / external APIs    │
└──────────────┬───────────────┘
               │
               └── implements ports defined inward
```

Dependencies should point toward the domain.

The domain must not depend on:

- web frameworks,
- database drivers,
- cloud SDKs,
- HTTP clients,
- CLI frameworks,
- concrete persistence implementations.

---

## 4. Layer responsibilities

## 4.1 Domain

The domain contains business concepts and rules.

Typical contents:

- entities,
- value objects,
- domain services,
- domain errors,
- business invariants,
- interfaces/ports required by domain behavior.

The domain should be:

- framework-independent,
- deterministic where possible,
- easy to unit test,
- free from direct network/database/filesystem access.

Example:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Money:
    amount: int

    def add(self, other: "Money") -> "Money":
        return Money(self.amount + other.amount)
```

Avoid:

```python
class Order:
    def save_to_postgres(self) -> None:
        ...
```

Persistence is not a domain responsibility.

---

## 4.2 Application

The application layer coordinates use cases.

Typical responsibilities:

- orchestration,
- transaction boundaries,
- calling domain logic,
- calling repository/service ports,
- mapping between domain objects and DTOs,
- authorization decisions when they are use-case specific.

Example:

```python
class CreateOrder:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    def execute(self, command: CreateOrderCommand) -> OrderId:
        order = Order.create(command.items)
        self._repository.save(order)
        return order.id
```

The application layer should not contain framework-specific request/response objects.

---

## 4.3 Infrastructure

Infrastructure implements technical details.

Examples:

- PostgreSQL repositories,
- REST/GraphQL clients,
- filesystem adapters,
- message brokers,
- cloud services,
- metrics exporters,
- concrete clock/random providers.

Infrastructure may depend on:

- domain-defined ports,
- application-defined ports,
- external libraries.

Infrastructure must not become the location for business rules.

---

## 4.4 Interfaces

Interfaces translate external inputs into application calls.

Examples:

- FastAPI routes,
- CLI commands,
- scheduled jobs,
- message consumers.

Responsibilities:

1. parse input,
2. validate transport-level syntax,
3. call an application use case,
4. map results/errors into the external protocol.

Interfaces should remain thin.

Bad:

```python
@router.post("/orders")
def create_order(request):
    # hundreds of lines of business logic
    ...
```

Good:

```python
@router.post("/orders")
def create_order(request: CreateOrderRequest):
    command = request.to_command()
    result = create_order_use_case.execute(command)
    return CreateOrderResponse.from_result(result)
```

---

## 5. Ports and adapters

Use ports only at boundaries where substitution or isolation provides real value.

Typical ports:

```python
from typing import Protocol


class OrderRepository(Protocol):
    def save(self, order: Order) -> None:
        ...

    def get(self, order_id: OrderId) -> Order | None:
        ...
```

Concrete infrastructure:

```python
class SqlOrderRepository:
    def save(self, order: Order) -> None:
        ...
```

Do not create interfaces for every class by default.

Create a port when at least one is true:

- the implementation is external or side-effecting,
- the dependency needs to be isolated for testing,
- multiple implementations are expected,
- inversion is necessary to preserve dependency direction.

---

## 6. Data flow

Typical request flow:

```text
External Input
    ↓
Interface
    ↓
DTO / Command / Query
    ↓
Application Use Case
    ↓
Domain Logic
    ↓
Port
    ↓
Infrastructure Adapter
    ↓
External System
```

Response flow:

```text
External System
    ↓
Infrastructure Adapter
    ↓
Application
    ↓
Result DTO
    ↓
Interface
    ↓
External Response
```

Domain objects should not leak directly into transport-specific schemas unless the project is intentionally trivial.

---

## 7. Configuration

Configuration should be loaded near application startup.

Recommended flow:

```text
environment variables / config file
        ↓
configuration loader
        ↓
typed settings object
        ↓
bootstrap / dependency wiring
```

Rules:

- validate required configuration early,
- never read environment variables deep inside domain logic,
- never hard-code credentials,
- inject environment-specific values from the composition root.

---

## 8. Composition root

Object construction and dependency wiring should happen in one obvious place.

Recommended location:

```text
src/<package>/bootstrap.py
```

or framework-equivalent startup code.

Example:

```python
def build_application(settings: Settings) -> Application:
    repository = SqlOrderRepository(settings.database_url)
    create_order = CreateOrder(repository)
    return Application(create_order=create_order)
```

Avoid constructing infrastructure dependencies throughout business code.

---

## 9. Error model

Errors should be separated by responsibility.

Example:

```text
DomainError
├─ InvalidOrderError
└─ InsufficientBalanceError

ApplicationError
├─ ResourceNotFoundError
└─ ConflictError

InfrastructureError
├─ DatabaseUnavailableError
└─ ExternalServiceError
```

Transport mapping belongs at the interface boundary.

Example:

```text
ResourceNotFoundError
        ↓
HTTP 404
```

The domain should not raise HTTP-specific exceptions.

---

## 10. Transactions

Transaction boundaries belong at the application/use-case level.

A use case should either:

- complete coherently, or
- fail without leaving invalid partial state.

Do not scatter transaction management through domain entities.

---

## 11. Observability

Logging, metrics, and tracing are cross-cutting concerns.

Rules:

- log at system boundaries,
- include useful identifiers,
- avoid duplicate exception logging,
- never log secrets,
- avoid embedding observability library APIs in core domain code unless justified.

---

## 12. Testing strategy

The architecture should support the following test pyramid:

```text
        E2E
       /   \
 Integration
 /         \
Unit Tests
```

Recommended focus:

- domain → mostly unit tests,
- application → unit tests with fake/mock ports,
- infrastructure → integration tests,
- interfaces → integration/contract tests,
- critical user journeys → limited E2E tests.

See `docs/rules/testing.md`.

---

## 13. External integrations

Every external system should have a clear adapter boundary.

Examples:

```text
domain/application port
        ↓
infrastructure adapter
        ↓
external API
```

Do not let vendor SDK types spread throughout the application.

Translate vendor-specific data into project-owned types at the adapter boundary.

---

## 14. Database access

Database-specific code belongs in infrastructure.

Recommended separation:

```text
domain model
    ≠
database ORM model
```

They may be the same representation in very small projects, but this should be an explicit simplification rather than an accidental coupling.

Migrations are part of infrastructure and must be reviewed together with schema-dependent code.

---

## 15. API boundaries

Public APIs should be stable and explicit.

Changes to:

- HTTP schemas,
- CLI commands,
- public Python APIs,
- message schemas,
- persisted data formats,

should be treated as compatibility-sensitive changes.

Breaking changes require explicit approval and documentation.

---

## 16. Dependency policy

Before adding a dependency:

1. check whether the standard library is sufficient,
2. check whether an existing dependency already solves the problem,
3. prefer actively maintained and narrowly scoped libraries,
4. avoid introducing framework-level dependencies into the domain,
5. update lock files,
6. validate the full test suite.

---

## 17. Architectural decision records

Significant architectural changes should be recorded in:

```text
docs/decisions/
```

Recommended format:

```text
ADR-001-short-title.md
ADR-002-short-title.md
```

Use an ADR when changing:

- persistence technology,
- message architecture,
- major framework,
- public API style,
- core domain boundaries,
- dependency inversion strategy,
- deployment architecture.

Suggested ADR sections:

```md
# ADR-XXX: Title

## Status

Accepted

## Context

## Decision

## Consequences

## Alternatives Considered
```

---

## 18. What not to over-engineer

Do not introduce architecture for architecture's sake.

Avoid prematurely adding:

- repository interfaces around trivial in-memory data,
- event buses for simple function calls,
- plugin systems without multiple plugins,
- factories for one implementation,
- abstract base classes with one subclass,
- microservices without deployment/domain justification.

Start simple and introduce boundaries when complexity requires them.

---

## 19. Architecture review checklist

Before merging a structural change, verify:

- Does the dependency direction still point inward?
- Is business logic kept out of infrastructure/interfaces?
- Are external systems behind clear boundaries?
- Is new abstraction solving a current problem?
- Can the changed behavior be tested without real external services?
- Did the change introduce unnecessary coupling?
- Does configuration remain outside the domain?
- Are public interfaces intentionally changed?
- Does this require an ADR?

---

## 20. Current project-specific decisions

Fill this section as the project evolves.

### Runtime

- Python: `>=3.11`
- Package manager: `uv`

### Quality

- Formatter/Linter: Ruff
- Type checker: mypy
- Test framework: pytest

### Architecture

- Style: lightweight layered / hexagonal
- Primary dependency direction: inward toward domain
- Composition root: `src/<package>/bootstrap.py`

### Persistence

- `<TBD>`

### External APIs

- `<TBD>`

### Deployment

- `<TBD>`
