# Architecture Rules

This document defines implementation-level architecture rules for humans and coding agents.

`ARCHITECTURE.md` describes the system structure.
This file defines what changes are allowed and where code should live.

---

## 1. Core rule

Dependencies must point toward the domain.

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

The following dependency is forbidden:

```text
domain → infrastructure
```

The following dependency is also normally forbidden:

```text
domain → interfaces
application → interfaces
```

---

## 2. Placement rules

Before creating a file, determine its responsibility.

### Put code in `domain/` when it defines:

- entities,
- value objects,
- domain invariants,
- domain services,
- domain errors,
- domain-facing ports.

### Put code in `application/` when it defines:

- use cases,
- commands,
- queries,
- orchestration,
- application DTOs,
- transaction coordination,
- application-facing ports.

### Put code in `infrastructure/` when it defines:

- database access,
- external API clients,
- filesystem access,
- message brokers,
- cloud SDK integrations,
- concrete adapters,
- environment/config implementations.

### Put code in `interfaces/` when it defines:

- HTTP routes,
- CLI commands,
- scheduled jobs,
- event/message consumers,
- protocol-specific request/response mapping.

If placement is unclear, prefer the layer with the narrowest responsibility and avoid creating a new top-level layer without a clear reason.

---

## 3. Domain purity

Domain code must not directly import or depend on:

- FastAPI,
- Flask,
- Django,
- SQLAlchemy,
- boto3,
- requests/httpx clients,
- Click/Typer,
- database drivers,
- cloud SDKs,
- filesystem paths used for I/O,
- environment-variable readers.

Domain code may use:

- Python standard library,
- project-owned domain types,
- carefully justified pure utility libraries.

Domain behavior should remain runnable in unit tests without external services.

---

## 4. Application layer rules

Application code may:

- depend on domain code,
- depend on abstract ports,
- orchestrate multiple domain operations,
- define use-case-level DTOs.

Application code should not:

- contain SQL,
- make raw HTTP calls,
- read environment variables directly,
- depend on framework request/response objects,
- contain persistence-specific mappings unless intentionally acting as a boundary.

---

## 5. Infrastructure rules

Infrastructure code may use third-party SDKs and concrete technologies.

Infrastructure should:

- implement project-owned ports,
- translate external errors into project-owned errors where appropriate,
- translate vendor data into project-owned types,
- isolate framework/vendor APIs from inner layers.

Infrastructure must not become the default location for business rules.

Bad:

```python
class SqlOrderRepository:
    def save(self, order: Order) -> None:
        if order.total > 100_000:
            order.apply_discount()
        ...
```

Business rules belong inward.

---

## 6. Interface rules

Interface code should remain thin.

A route/CLI handler should primarily:

1. parse input,
2. validate protocol-level syntax,
3. convert to application input,
4. call one or more use cases,
5. map result/errors to the external protocol.

Avoid performing domain calculations directly in interface code.

---

## 7. Port creation rules

Do not create an interface or `Protocol` automatically for every concrete class.

Create a port when one or more apply:

- external side effects need isolation,
- dependency inversion is required,
- multiple implementations are realistic,
- unit testing benefits materially,
- the boundary is architecturally significant.

Avoid speculative abstraction.

---

## 8. Dependency injection

Prefer constructor/function injection for external dependencies.

Good:

```python
class CreateOrder:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository
```

Avoid hidden global construction:

```python
repository = SqlOrderRepository(...)


def create_order(...):
    repository.save(...)
```

Object construction should be concentrated near the composition root.

---

## 9. Framework isolation

Framework-specific types should stop at the interface boundary whenever practical.

Examples:

- FastAPI `Request` should not enter the domain.
- SQLAlchemy model objects should not become domain APIs by accident.
- boto3 response dictionaries should be mapped to project-owned types.
- vendor exceptions should not leak across layers unnecessarily.

---

## 10. Data models

Use different models when responsibilities differ.

Common categories:

```text
Transport schema
Application DTO
Domain model
Persistence model
External vendor model
```

Do not create five representations when one simple representation is sufficient.

But do not force one model to serve unrelated responsibilities merely to avoid mapping code.

---

## 11. Cross-layer helpers

Avoid generic dumping grounds such as:

```text
utils.py
helpers.py
common.py
misc.py
```

Prefer responsibility-specific modules.

Instead of:

```text
utils.py
```

prefer:

```text
date_parsing.py
currency.py
retry_policy.py
```

A helper used by only one module should usually remain near that module.

---

## 12. Circular dependencies

Do not fix circular imports with ad-hoc local imports as the default solution.

First inspect whether:

- responsibilities are mixed,
- a shared concept belongs in the domain,
- a port should invert the dependency,
- modules should be split or merged.

A local import is acceptable only when the dependency itself is architecturally valid and the import cycle is incidental.

---

## 13. Shared state

Avoid mutable global state.

Prefer explicit ownership of:

- clients,
- repositories,
- caches,
- clocks,
- random generators,
- configuration.

Global constants are acceptable when they are immutable and truly global domain/configuration constants.

---

## 14. Configuration boundaries

Environment variables and config files must be read near startup/configuration code.

Do not do this inside domain or application logic:

```python
api_key = os.environ["API_KEY"]
```

Prefer:

```python
settings = load_settings()
client = ExternalClient(settings.api_key)
```

and inject the resulting dependency.

---

## 15. Time and randomness

Business logic that depends on time/randomness should make those dependencies testable.

Prefer:

```python
def expire_session(session: Session, now: datetime) -> Session:
    ...
```

over:

```python
def expire_session(session: Session) -> Session:
    now = datetime.now()
```

For complex cases, use explicit clock/random provider abstractions.

---

## 16. Database boundaries

SQL and ORM queries belong in infrastructure.

Rules:

- use parameterized queries,
- keep transaction boundaries explicit,
- avoid lazy-loading behavior leaking unpredictably into application/domain code,
- add migration changes together with schema-dependent code,
- test repository behavior with integration tests.

---

## 17. External service boundaries

External API clients should be wrapped by project-owned adapters when they are part of core behavior.

The rest of the codebase should depend on a project-owned interface, not vendor response formats.

Bad:

```python
def calculate_price(stripe_response: dict) -> int:
    ...
```

Better:

```python
@dataclass(frozen=True)
class PaymentStatus:
    paid: bool
    amount: int
```

Translate at the infrastructure boundary.

---

## 18. Error boundaries

Do not leak transport/framework-specific exceptions inward.

Examples of prohibited inward leakage:

```text
HTTPException
SQLAlchemyError
botocore ClientError
```

Translate errors at appropriate boundaries.

Example:

```text
botocore ClientError
        ↓
ObjectStorageUnavailableError
```

---

## 19. Public APIs

Changes to public interfaces require extra care.

Public interfaces include:

- exported Python functions/classes,
- HTTP endpoints,
- CLI commands,
- serialized messages,
- persistent file formats,
- DB schemas used externally.

When changing one:

1. identify consumers,
2. preserve compatibility when required,
3. update tests,
4. update docs,
5. create an ADR if the change is architectural.

---

## 20. New dependencies

Before introducing a dependency:

1. search existing project capabilities,
2. evaluate standard library alternatives,
3. confirm maintenance/security posture,
4. keep it out of the domain unless it is pure and justified,
5. update `pyproject.toml`,
6. update `uv.lock`,
7. run full validation.

Do not add dependencies solely to save a few lines of straightforward code.

---

## 21. New modules and packages

Create a new module when:

- it has a clear independent responsibility,
- the current module is becoming hard to reason about,
- the boundary improves testability or dependency clarity.

Do not create modules merely to satisfy arbitrary file-size limits.

Create a new top-level package/layer only when there is a stable architectural distinction.

---

## 22. Refactoring rules

Architecture refactoring should be incremental.

Prefer:

```text
move one responsibility
→ update imports
→ update tests
→ validate
```

over large speculative rewrites.

Do not combine broad architecture cleanup with unrelated feature work unless necessary.

---

## 23. Architecture changes requiring explicit attention

The following changes should normally trigger an architecture review and possibly an ADR:

- adding a new top-level layer,
- adding a new database,
- replacing the persistence technology,
- introducing a message broker,
- splitting into services,
- introducing a new framework,
- changing public API style,
- introducing a plugin system,
- changing core dependency direction,
- changing transaction boundaries,
- introducing distributed state.

---

## 24. Agent workflow

Before making an architectural change, Codex should:

1. inspect nearby modules,
2. read `ARCHITECTURE.md`,
3. identify existing dependency direction,
4. search for existing ports/adapters/helpers,
5. minimize the number of new abstractions,
6. state any architectural assumption when it is not obvious,
7. run tests and static checks after the change.

Codex should not create a new architecture pattern when the repository already has a coherent one.

---

## 25. Review checklist

For each non-trivial code change, verify:

- Is the code in the correct layer?
- Did any dependency start pointing outward from the domain?
- Did framework/vendor types leak inward?
- Is business logic accidentally placed in an adapter?
- Is a new abstraction solving a current need?
- Is dependency injection explicit?
- Can the behavior be unit tested?
- Are external side effects isolated?
- Are errors translated at boundaries?
- Did configuration leak into business logic?
- Does the change require an ADR?

---

## 26. Exceptions

Architecture rules may be intentionally relaxed for:

- very small scripts,
- prototypes,
- migration code,
- performance-critical code,
- framework constraints.

An exception should be explicit and local.

If the exception becomes permanent or spreads across the codebase, document the decision in `ARCHITECTURE.md` or an ADR.
