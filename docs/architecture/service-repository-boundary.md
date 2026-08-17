# Service vs Repository Boundary

Type: architecture
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-13
Purpose: Define the repeatable boundary between service and repository layers — what belongs where and why.
Related: [Architecture Conventions](architecture-conventions.md), [Service Cookbook](service-cookbook.md), [Trading Package Map](../maps/trading-package-map.md)

This note defines the repeatable boundary for modules that have both a
`src/trading/services/*` and `src/trading/repositories/*` layer.

## Goal

Make the split easy to reason about:

- **repositories** answer "how is this data stored and queried?"
- **services** answer "what is the application trying to do?"

The layers work best when the public service API expresses use cases, while the
repository API expresses persistence primitives.

## Repository responsibilities

Repositories own persistence details:

1. SQL shape (`SELECT`, `INSERT`, `UPDATE`, `DELETE`)
2. column names, table names, joins, ordering, and pagination
3. row materialization (`sqlite3.Row` -> typed record / dict)
4. generic persistence primitives that services can compose

Repository functions may still be specific and useful. For example,
`fetch_by_name()` is an acceptable repository helper because it is a
common persistence query, not business logic.

Repository functions should **not**:

1. normalize caller input with business meaning
2. apply application defaults or policy rules
3. decide whether missing data is acceptable
4. raise caller-facing workflow errors when a use case fails

## Service responsibilities

Services own application intent:

1. validation and normalization of caller input
2. not-found behavior (`None` vs raised error)
3. orchestration across repositories and other services
4. caller-facing semantics and naming
5. use-case-specific shaping of lower-level repository helpers

Good service function names usually describe the use case:

- `get_account()` -> strict lookup, raises when missing
- `find_account()` -> optional lookup, returns `None`
- `list_account_records()` -> caller-facing account listing rules
- `list_account_snapshots()` -> validates limit and delegates to snapshot storage
- `set_account_strategy()` -> validates strategy changes before persisting

## Public service surface

External callers should prefer the service layer. However, that does **not**
mean the service module should mirror repository names one-for-one.

Import from the module that owns a capability, not a package-root re-export.
`execution` and `books` are the model. Use
[service-cookbook.md](service-cookbook.md) for the current capability → module
lookup.

Do **not** add a re-export `__init__.py` facade or a sibling shim that only
forwards another module's symbols. That creates two public APIs for the same
capability and reintroduces redirect-only wrappers. Several packages still carry
a legacy `__all__` facade from an earlier convention; retire each as its package
is touched, migrating callers to the owning module first.

Avoid public service helpers that are only passthroughs like:

```python
def fetch_by_name(conn, name):
    return AccountRepository(conn).fetch_by_name(name)
```

If a service function adds no validation, orchestration, fallback behavior, or
use-case meaning, either:

1. remove it from the public service API, or
2. replace it with a service-shaped function that does add those semantics.

## Mutation pattern

For writes, prefer:

1. a **generic repository primitive** for persistence mechanics
2. **specific service helpers** for business intent

Example:

- repository: `update(...)`
- service: `set_account_strategy(...)`, `set_benchmark(...)`, `configure_account(...)`

This keeps SQL assembly in the repository while keeping validation and policy in
the service layer.

If persistence writes still need invariant checks, keep those checks in the
service mutation helper rather than embedding policy validation into the
repository primitive.

## Refactor checklist

Use this checklist when cleaning another service/repository pair:

1. List public service functions and mark which are passthroughs.
2. Keep repository helpers that encapsulate common SQL patterns.
3. Rename or replace service passthroughs with use-case-oriented helpers.
4. Move not-found handling, validation, and normalization into services.
5. Keep row mapping and SQL filters/order clauses inside repositories.
6. Update callers to use the service vocabulary.
7. Collapse onto a single stable service import surface for the capability.
8. Remove redundant service exports/modules once callers are migrated.

## Core Examples

### Account lookup and mutation

For `accounts`:

- repository remains responsible for:
  - `fetch_by_name`
  - `fetch_by_id`
  - `fetch_all`
  - `update`
- service should expose:
  - `find_account`
  - `get_account`
  - `list_account_records`
  - `list_account_names`
  - `list_account_snapshots`
  - `get_latest_account_snapshot`
  - `set_account_strategy`

Import each from the module inside `trading.services.accounts` that owns it.

That split keeps repository files table-shaped and service files workflow-shaped.

### Operational settings

For the operational-settings slice:

- `trading.services.operational_settings` owns the caller-facing trade throttle,
  evaluation-confidence, and promotion-policy settings,
  even though those reads still use `global_settings` underneath.
- It should also own validation for write-side invariants such as normalized
  evaluation-confidence weights; the repository should only persist the provided
  row shape.
- The same package root also owns trade-cap throttle enforcement
  (`enforce_runtime_trade_throttles`), even though it still uses `trades`
  for the persistence query.

Not every `runtime_*` module needs to become a package. A tiny constants module
like `runtime_job_status.py` can remain standalone when it is already a clear
surface and does not duplicate a sibling facade or blur a service/repository
boundary.

### Evaluation and auto-trading package splits

For strategy evaluation flows:

- `trading.services.evaluation` owns caller-facing evaluation reads; import each
  from the module inside it that owns the read.
- internal evidence-building helpers live beneath the package root without a
  re-export facade.

## Auto-trading example

For the runtime trading cluster:

- `trading.services.auto_trading` owns runtime auto-trading orchestration,
  market/input preparation, and rotation bridge helpers across its `runtime`,
  `inputs`, and `market` modules; import from the owning module.
- execution and rotation internals live beneath the package root without sibling
  facades.

### Book execution and parameters

For the clean book-keyed runtime:

- `trading.services.books` owns book assignments, rotation, trade-candidate
  generation, and book-local reporting helpers.
- `trading.services.execution.*` owns the shared submit/persist/on-fill path and
  the pre-submit gate seam used by every book. Keep imports focused on the
  submodule that owns the specific execution concern.
- `trading.services.strategy_catalog` owns strategy catalog seeding,
  primitive-plus-parameter resolution, and catalog edits.
- `trading.services.parameters` owns the unified parameter source view and
  edit workflows over the existing owning stores; it is not a new persistence
  layer.
