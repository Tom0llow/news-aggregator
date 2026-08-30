# news-aggregator

Python project scaffold for a news aggregation application.

The repository is currently in bootstrap state: the development, CI, review, and
guarded Codex automation foundations are present; product behavior is added from
explicit requirements.

## Development

Requires Python 3.11+ and `uv`.

```powershell
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv run pytest --cov=src --cov-report=term-missing --cov-report=xml
```

## Autonomous Codex workflow

Non-trivial implementation/bug-fix requests are routed through
`autonomous-task`:

```text
requirement
→ preflight
→ agent/* branch
→ implementation
→ independent review/fix
→ validation
→ guarded commit/push/PR
→ Quality + Test
→ final PR review
→ MERGE_READY
→ exact-HEAD human approval
→ guarded squash merge
```

See:

- `AGENTS.md`
- `ARCHITECTURE.md`
- `docs/AUTONOMOUS_DEVELOPMENT.md`
- `docs/rules/`
- `docs/decisions/`

## Repository policy

`main` is protected. Autonomous code must not bypass the guarded wrappers with
raw branch/commit/push/merge commands.
