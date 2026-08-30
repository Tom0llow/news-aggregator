# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs).

ADRs preserve the reasoning behind decisions that are expensive, risky, or confusing to rediscover later.

They are intended for both humans and coding agents.

---

## 1. When to create an ADR

Create an ADR when a decision has a meaningful long-term effect on the system.

Typical examples:

- adopting or replacing a framework,
- choosing a database or storage technology,
- introducing a message broker,
- changing architecture boundaries,
- changing dependency direction,
- introducing a new external service,
- changing authentication/authorization strategy,
- introducing a cache,
- adopting a deployment platform,
- adding a major dependency that shapes the architecture,
- changing public API style,
- changing persistence/data formats,
- introducing background jobs,
- splitting a monolith into services,
- introducing a plugin/event architecture.

Do not create an ADR for trivial implementation details.

Examples that normally do **not** need an ADR:

- renaming a private function,
- adding a small helper,
- fixing a bug without architectural impact,
- adding a test,
- changing formatting,
- routine dependency patch updates.

---

## 2. File naming

Use sequential numbering:

```text
ADR-000-template.md
ADR-001-use-postgresql.md
ADR-002-use-fastapi.md
ADR-003-introduce-background-jobs.md
```

Use:

```text
ADR-NNN-short-kebab-case-title.md
```

Rules:

- never reuse an ADR number,
- never renumber existing ADRs,
- keep titles short and descriptive,
- use present-tense decision wording when practical.

---

## 3. ADR lifecycle

Supported statuses:

```text
Proposed
Accepted
Deprecated
Superseded
Rejected
```

### Proposed

The decision is under discussion.

### Accepted

The decision is active and should guide implementation.

### Deprecated

The decision is no longer recommended, but may still exist in the system.

### Superseded

A newer ADR replaces this decision.

When superseding an ADR, reference the new ADR explicitly.

Example:

```text
Status: Superseded by ADR-012
```

### Rejected

The option was considered and explicitly rejected.

Rejected ADRs can still be valuable because they prevent the same discussion from repeating.

---

## 4. ADR structure

Start from:

```text
ADR-000-template.md
```

Every ADR should explain:

1. **Context** — what problem or constraint exists?
2. **Decision** — what are we choosing?
3. **Rationale** — why is this option preferred?
4. **Consequences** — what becomes easier/harder?
5. **Alternatives Considered** — what else was evaluated?
6. **Validation / Follow-up** — how will we know the decision works?

The document should capture reasoning, not just the final choice.

---

## 5. Decision quality

A useful ADR should be understandable without reconstructing the original conversation.

Prefer concrete statements.

Bad:

```text
We chose PostgreSQL because it is better.
```

Better:

```text
We chose PostgreSQL because the application requires transactional updates,
relational constraints, and predictable support for concurrent writes.
```

Record important tradeoffs.

Example:

```text
This increases operational complexity compared with SQLite, but removes the
single-process write limitations that conflict with the deployment model.
```

---

## 6. Relationship with other documentation

Use:

```text
ARCHITECTURE.md
```

for the **current architecture**.

Use:

```text
docs/decisions/
```

for **why important architecture decisions were made**.

Use:

```text
docs/rules/architecture.md
```

for **implementation rules that must be followed**.

The relationship is:

```text
ADR
  ↓ explains why
ARCHITECTURE.md
  ↓ describes what exists
architecture rules
  ↓ defines how changes must preserve it
```

---

## 7. Updating architecture after an ADR

When an ADR is accepted and changes current architecture:

1. add/update the ADR,
2. update `ARCHITECTURE.md`,
3. update `docs/rules/architecture.md` if implementation rules changed,
4. update tests/CI/configuration if required.

Do not leave accepted ADRs disconnected from the current architecture documentation.

---

## 8. Codex / agent rules

Before making a significant architectural change, coding agents should:

1. read `ARCHITECTURE.md`,
2. read `docs/rules/architecture.md`,
3. inspect relevant ADRs,
4. determine whether the change requires a new ADR,
5. avoid silently contradicting an accepted ADR.

Agents must not rewrite historical ADR reasoning to make current code appear consistent.

If a previous decision changes:

- preserve the old ADR,
- create a new ADR,
- mark the old ADR as `Superseded`.

---

## 9. Searching ADRs

Before creating a new ADR, search for existing decisions related to:

- the affected subsystem,
- the proposed technology,
- the relevant architectural boundary,
- rejected alternatives.

Avoid creating duplicate ADRs for the same decision.

---

## 10. Review checklist

Before accepting an ADR, verify:

- Is the problem/context clear?
- Is the decision explicit?
- Are the main constraints documented?
- Are important alternatives listed?
- Are tradeoffs acknowledged?
- Are negative consequences documented?
- Is the scope clear?
- Does the decision conflict with an existing ADR?
- Does `ARCHITECTURE.md` need updating?
- Are follow-up actions concrete?

---

## 11. Recommended workflow

```text
Problem identified
      ↓
Search existing ADRs
      ↓
Create ADR as Proposed
      ↓
Evaluate alternatives
      ↓
Review decision
      ↓
Accept / Reject
      ↓
Update ARCHITECTURE.md and rules
      ↓
Implement
      ↓
Validate consequences
```

---

## 12. Minimal ADR policy

Do not create ADRs merely to create documentation.

The goal is not to document every decision.

The goal is to preserve decisions whose reasoning would otherwise be costly to recover.
