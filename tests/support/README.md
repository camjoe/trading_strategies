# Test Support

## Purpose

`tests/support/` is the shared helper layer for repeated test fixtures, fakes, seed data, and small harnesses.

The package is intentionally organized by test area rather than as one large utility module. Examples include:

- `tests.support.auto_trading`
- `tests.support.backtesting`
- `tests.support.cli_main`
- `tests.support.runtime_jobs`
- `tests.support.seed_db`

## Key Modules

### `seed_db.py`

Defines `seed_session_db(conn)` and the named constants used by `seeded_conn` tests:

```
ACCT_TREND, ACCT_MOMENTUM, ACCT_PASSIVE
SLEEVE_TREND, SLEEVE_MOMENTUM
SNAPSHOT_T1, SNAPSHOT_T2, SNAPSHOT_T3
```

Reference these constants instead of hard-coding string literals. New entities added to the seed should get a named constant here.

### `auto_trading.py`

Factory helpers that return **real production types** (not `SimpleNamespace`):

- `make_account_state(*, cash, positions, avg_cost, realized_pnl)` → `AccountState`
- `make_feature_bundle(*, available, **features)` → `ExternalFeatureBundle`
- `make_feature_fetcher(bundles_by_ticker, *, available)` → `Callable[[str], ExternalFeatureBundle]`
- `make_runtime_scenario(...)` → `RuntimeScenario`

### `backtesting.py`

- `make_backtest_result(**overrides)` → `BacktestResult` with sensible zero defaults.
- `make_backtest_leaderboard_entry(**overrides)` → `BacktestLeaderboardEntry`.

### `repositories.py`

Raw-SQL insert helpers for repository-layer tests that need to write data without going through service validation (e.g. `insert_repository_account`).

## Usage

- Prefer adding new helpers to the most specific module possible.
- Prefer direct imports from the specific helper module when a helper is only used by one area.
- Use real production types (dataclasses, domain models) in helpers — not `SimpleNamespace` — unless the type comes from an external boundary that is impractical to construct.
- Avoid treating `tests/support/__init__.py` as the default place to expose every helper.

## Notes

- The main risk of drift is `tests/support/__init__.py` becoming a broad utility dump that hides ownership and encourages unrelated coupling. When this area drifts, review `__init__.py` first before splitting into more files.
