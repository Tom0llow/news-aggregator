# Architecture — news-aggregator

## Status

Bootstrap architecture.

The repository currently contains the development harness and a minimal Python
package skeleton. Product behavior, external sources, persistence, delivery
interfaces, and deployment choices are not yet defined in the repository.

Agents must not invent those decisions. Implement them only from explicit
requirements or an Accepted ADR.

## Runtime and tooling

- Python: 3.11+
- Package/environment manager: uv
- Formatter/linter: Ruff
- Type checker: mypy
- Tests: pytest
- CI: GitHub Actions

## Architectural style

Use a lightweight layered / hexagonal style only as the application earns the
complexity.

Dependency direction:

```text
interfaces
    ↓
application
    ↓
domain

infrastructure
    ↓
application/domain ports
```

Core domain/application code must not depend directly on concrete HTTP clients,
database drivers, cloud SDKs, or CLI/web frameworks.

## Current package

```text
src/news_aggregator/
├─ __init__.py
└─ main.py
```

Do not create every possible layer/directory in advance.

Add a layer or port when real behavior requires it.

## Expected responsibilities

### domain

Pure project-owned concepts, invariants, and deterministic behavior.

No direct network, database, filesystem, framework, or environment access.

### application

Use-case orchestration.

Coordinates domain behavior and ports.

### infrastructure

Concrete external details such as HTTP/RSS/API clients, persistence, filesystem,
or cloud adapters.

### interfaces

Thin external entry points such as CLI, HTTP API, or scheduled jobs.

### composition root

Dependency construction belongs in one obvious bootstrap/startup location.

## News-source boundary

When source integrations are introduced, vendor/source-specific response types
must be translated into project-owned types at the infrastructure boundary.

Do not let one source's schema become the application's domain model.

## Configuration

Read environment/configuration near startup and convert it into typed
project-owned settings.

Never read environment variables from domain logic.

Never commit credentials or tokens.

## Error boundaries

Keep protocol/vendor errors at external boundaries.

Translate them into project-owned application/domain errors where useful.

Do not raise HTTP-specific errors from the domain.

## Testing

Prefer:

- domain/application: fast unit tests
- infrastructure adapters: focused integration tests
- external protocols: contract/integration tests
- end-to-end: only critical flows

Behavioral changes require meaningful tests.

The bootstrap import test is not a substitute for feature behavior tests.

## ADRs

Create an ADR for durable choices such as:

- source ingestion strategy
- persistence technology
- scheduling/execution model
- public API/CLI contract
- deduplication/identity policy
- deployment architecture
- major framework adoption

Accepted ADRs override assumptions and must not be silently contradicted.

## Non-goals

Do not introduce:

- repositories/ports with no boundary need
- event buses for simple calls
- plugin systems without actual plugins
- abstract base classes with one implementation
- microservices without a concrete deployment/domain reason

Keep the design proportional to current requirements.
