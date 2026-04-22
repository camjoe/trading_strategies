# Service vs Repository Boundary

This note defines the repeatable boundary for modules that have both a
`trading/services/*` and `trading/repositories/*` layer.

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
`fetch_account_by_name()` is an acceptable repository helper because it is a
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

## Public facade rule

External callers should prefer the service layer. However, that does **not**
mean the service module should mirror repository names one-for-one.

Prefer **one** stable public service surface per capability. In practice, that
usually means the package root when a capability already has an internal split,
for example:

- `trading.services.accounts`
- `trading.services.accounting`
- `trading.services.reporting`
- `trading.services.promotion`
- `trading.services.admin`
- `trading.services.profiles`
- `trading.services.runtime_settings`
- `trading.services.runtime_throttle`

Do **not** keep a second sibling facade such as `accounts_service.py` once the
package root already serves as the stable import surface. That creates two
public APIs for the same capability and reintroduces redirect-only wrappers.

Avoid public service helpers that are only passthroughs like:

```python
def fetch_account_by_name(conn, name):
    return repo_fetch_account_by_name(conn, name)
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

- repository: `update_account_fields(...)`
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

## Accounts example

For `accounts`:

- repository remains responsible for:
  - `fetch_account_by_name`
  - `fetch_account_rows`
  - `fetch_account_listing_rows`
  - `update_account_fields`
- service should expose:
  - `find_account`
  - `get_account`
  - `list_account_records`
  - `list_account_names`
  - `list_account_snapshots`
  - `get_latest_account_snapshot`
  - `set_account_strategy`

The stable public import surface should be `trading.services.accounts`, not both
`trading.services.accounts` and `trading.services.accounts_service`.

That split keeps repository files table-shaped and service files workflow-shaped.

## Runtime example

For the small runtime slice:

- `trading.services.runtime_settings` is the caller-facing package root for
  runtime throttle, evaluation-confidence, and promotion-policy settings,
  even though those reads still use `global_settings_repository` underneath.
- `trading.services.runtime_settings` should also own validation for write-side
  invariants such as normalized evaluation-confidence weights; the repository
  should only persist the provided row shape.
- `trading.services.runtime_throttle` is the caller-facing package root for
  enforcing trade-cap policy, even though it still uses `trades_repository`
  for the persistence query.

Not every `runtime_*` module needs to become a package. A tiny constants module
like `runtime_job_status.py` can remain standalone when it is already a clear
surface and does not duplicate a sibling facade or blur a service/repository
boundary.

## Profiles example

For profile application flows:

- `trading.services.profiles` is the stable public service surface for loading
  and applying account profiles.
- `trading.services.profile_source` can remain a separate source abstraction
  because it represents profile-input backends rather than a sibling facade for
  the same use-case API.
