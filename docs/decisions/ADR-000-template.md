# ADR-000: <Decision title>

- Status: Proposed
- Date: YYYY-MM-DD
- Decision Owners: <team / role / names if appropriate>
- Related Issues/PRs: <optional>
- Supersedes: <ADR-NNN or N/A>
- Superseded by: <ADR-NNN or N/A>

---

## Context

Describe the problem, constraint, or architectural pressure that requires a decision.

Include only context necessary to understand the decision.

Useful context may include:

- current system behavior,
- scale/performance requirements,
- deployment constraints,
- security requirements,
- operational requirements,
- team constraints,
- compatibility requirements,
- relevant existing ADRs.

Example questions:

- What problem are we solving?
- Why does the current approach no longer work?
- What constraints cannot be changed?
- What happens if we make no decision?

---

## Decision

State the decision clearly and concretely.

Prefer:

```text
We will use PostgreSQL as the primary transactional database.
```

Avoid vague wording such as:

```text
We should probably consider PostgreSQL.
```

Specify scope where necessary.

Example:

```text
This decision applies to application transactional data.
Analytics workloads remain outside the scope of this ADR.
```

---

## Rationale

Explain why this option was chosen.

Describe the criteria that mattered most.

Examples:

- correctness,
- maintainability,
- performance,
- operational simplicity,
- ecosystem maturity,
- security,
- cost,
- team familiarity,
- migration effort,
- testability.

Do not repeat the Decision section. Explain the reasoning.

---

## Consequences

### Positive

List meaningful benefits.

- <benefit>
- <benefit>

### Negative

List costs and drawbacks explicitly.

- <cost>
- <cost>

### Neutral / Follow-on effects

List changes that are neither inherently positive nor negative.

- <effect>
- <effect>

---

## Alternatives Considered

### Option A: <name>

Summary:

<brief description>

Advantages:

- <advantage>

Disadvantages:

- <disadvantage>

Reason not selected:

<reason>

### Option B: <name>

Summary:

<brief description>

Advantages:

- <advantage>

Disadvantages:

- <disadvantage>

Reason not selected:

<reason>

---

## Implementation Notes

Describe architectural implementation constraints created by this decision.

Examples:

- new package/module boundaries,
- migration requirements,
- required adapters/ports,
- compatibility requirements,
- rollout order,
- data migration strategy.

Avoid turning the ADR into a detailed task list.

---

## Validation

Describe how the decision will be validated.

Examples:

- performance benchmark,
- load test,
- production metric,
- integration test,
- migration rehearsal,
- security review.

Specify success criteria when meaningful.

Example:

```text
The new persistence layer must sustain 500 requests/second with p95 write
latency below 100 ms under the expected production workload.
```

---

## Risks

List important risks introduced by this decision.

For each material risk, include mitigation when possible.

| Risk | Impact | Mitigation |
| --- | --- | --- |
| <risk> | <impact> | <mitigation> |

---

## Security / Privacy Impact

State whether the decision affects:

- authentication,
- authorization,
- secrets,
- personal data,
- encryption,
- network exposure,
- data retention,
- auditability.

If there is no meaningful impact:

```text
No material security or privacy impact.
```

---

## Operational Impact

Describe effects on:

- deployment,
- monitoring,
- logging,
- backup/recovery,
- on-call operations,
- maintenance,
- infrastructure cost.

If none:

```text
No material operational impact.
```

---

## Migration / Rollback

If existing behavior/data must change, describe:

### Migration

<how the system moves to the new architecture>

### Rollback

<how the decision can be reversed if implementation fails>

If rollback is not practical, state that explicitly.

---

## Documentation Changes

When this ADR becomes Accepted, update as applicable:

- [ ] `ARCHITECTURE.md`
- [ ] `docs/rules/architecture.md`
- [ ] `AGENTS.md`
- [ ] `README.md`
- [ ] API/user documentation
- [ ] operational/runbook documentation

---

## Follow-up Actions

- [ ] <action>
- [ ] <action>

Avoid using this section as the project's primary task tracker.
Link to Issues/PRs for substantial implementation work.

---

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| YYYY-MM-DD | Proposed | Initial proposal |
