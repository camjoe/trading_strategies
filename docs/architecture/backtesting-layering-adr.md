# ADR: Backtesting Layering and Dependency Boundaries

Status: Accepted
Date: 2026-03-27

## Context

Backtesting behavior was previously concentrated in a single module that mixed:

- SQL reads and writes
- model mapping
- simulation and risk logic
- windowing and walk-forward orchestration
- transport-oriented wrapper outputs

This made it harder to test layers directly, reason about dependency direction, and keep changes low-risk.

## Decision

Adopt a layered structure for backtesting:

1. Repository layer
- Owns SQL statements and database row retrieval/persistence only.
- No business logic, no transport formatting.

2. Service layer
- Owns model mapping, calculations, and orchestration logic.
- Depends on repositories and domain helpers.

3. Domain helper modules
- Own focused, reusable pure logic (metrics, windowing, risk/warnings, simulation math).

4. Compatibility wrappers
- Keep existing public APIs stable while internals move behind layers.
- Wrappers convert typed models to legacy payload shapes where needed.

## Implementation Map

Use these docs for the current module map and ownership locations:

- `docs/backtesting.md`
- `trading/backtesting/README.md`

This ADR intentionally records the decision and guardrails, not a volatile file inventory.

## Consequences

Benefits:

- Smaller, focused modules with clear ownership.
- Easier contract tests at repository/service/domain levels.
- Safer refactors because wrappers preserve public behavior.
- Cleaner path to Controller -> Service -> Repository architecture.

Trade-offs:

- More files to navigate.
- Requires discipline to avoid slipping SQL/business logic back into entrypoint modules.

## Guardrails

When adding new backtesting features:

1. Put SQL in repository modules.
2. Put mapping and orchestration in service modules.
3. Put pure calculations/rules in domain helper modules.
4. Keep backtest.py focused on public API wrappers and high-level composition.
5. Add contract tests for each new repository/service/helper path.

## Why Not an ORM (for now)

Current needs are analytics-heavy and query-shape specific. Explicit SQL keeps intent and performance transparent. Revisit ORM only if object-graph complexity, relationship tracking, or portability pressure increases.
