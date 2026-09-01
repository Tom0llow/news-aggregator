# Architecture — news-aggregator

## Status

Implemented local application architecture. The durable choices are recorded in
`docs/decisions/ADR-001-local-news-aggregation-architecture.md` (Accepted).

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
├─ domain/          # article/source models and deterministic validation rules
├─ application/     # fetch/search orchestration and project-owned ports
├─ infrastructure/  # fixed source catalog, RSS/HTTP, SQLite, scheduler
├─ interfaces/      # local HTTP API, CLI boundary, and browser assets
├─ __init__.py
└─ main.py          # composition root and CLI
```

`main.py` is the only composition root. Importing modules does not start the
server, scheduler, network access, or database initialization.

## Runtime topology

One process owns an IPv4-loopback `ThreadingHTTPServer`, a fixed-interval
scheduler thread, short-lived SQLite connections in WAL mode, and one fetch-cycle
lock. The scheduler starts a background fetch after server startup and repeats
every 30 minutes. Feed exceptions are isolated. ASCII.jp's 60-minute interval is
enforced from its last successful attempt. Shutdown closes the server and joins
the scheduler thread.

## Persistence and time

SQLite schema changes use `PRAGMA user_version`. Articles have no expiry. A
database unique constraint protects `duplicate_key`, while the original URL is
retained for display. Feed attempts, successes, skips, and errors are stored
separately. Capacity is the sum of existing DB, WAL, SHM, and journal files.

Aware timestamps are stored in UTC. Search converts Japanese calendar-day bounds
to UTC; browser rendering uses `Asia/Tokyo`. A null timestamp is unknown. Yahoo!
RSS `pubDate` has the semantic type `portal_provided` and is never presented as
the original publisher's publication time.

## Local HTTP boundary

The server validates both the bind address and `Host` as IPv4 loopback. Fixed
static routes and same-origin JSON endpoints expose article search, source state,
storage usage, and manual fetching. There is no arbitrary URL fetch endpoint,
CORS opt-in, authentication, or server-side user profile.

The browser creates dynamic values with `textContent`. HTTP(S) article links open
with `noopener noreferrer`; content security policy forbids remote scripts,
styles, images, objects, and frames. Saved keywords and favorites use only
versioned browser `localStorage` keys.

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
