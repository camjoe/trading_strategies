# Test Infrastructure Progress

This document records what was built to improve the test suite on this branch, and why each decision was made. It is written for a returning author who needs to pick up where this work left off.

---

## Starting point and motivation

Before this work, the test suite had several friction points that made it harder to read and extend:

- **Repeated DB setup in every test.** Account creation, snapshot insertion, and trade records were written inline in individual test functions, often with slight variations in names and values. There was no shared language for "a standard test account" or "a standard sleeve."
- **Redundant fixture definitions.** At least two test files (`test_queries.py`, `test_daily_report.py`) each defined their own `conn` fixture that was byte-for-byte identical to the root conftest version, silently overriding it with no difference in behavior.
- **Long test bodies dominated by setup.** Tests like those in `test_runtime_sleeve_mode.py` spent 10–20 lines creating entities before reaching the assertion. The scenario being tested was buried.
- **Validation test duplication.** Tests that checked "this invalid input raises this error" were written as separate functions even when they differed only in the input value and the expected error message.
- **No shared test data vocabulary.** String literals like `"acct_trend"`, `"2026-05-03"`, and `"trend"` appeared across files with no central definition, making it unclear whether two tests were intentionally using the same account or coincidentally using the same name.

---

## What was built

### `tests/support/seed_db.py` — central seed module

**Decision:** Create a session-scoped seeded database as the authoritative "test universe."

**Why:** Tests that only read data should not pay the cost of creating it. More importantly, having a single source of truth for what entities exist in the test world makes the suite easier to reason about. If `ACCT_TREND = "acct_trend"` is defined in one place, you know every reference to it is intentional.

The seed covers: 3 accounts, 3 trades, 3 snapshots, 1 global settings row, 1 backtest run, 1 promotion review, 1 sleeve with a strategy assignment and a daily metric.

Named constants exported from this module (`ACCT_TREND`, `ACCT_MOMENTUM`, `SLEEVE_TREND`, `SNAPSHOT_T1`, etc.) are the shared vocabulary. Tests reference constants rather than string literals.

**What we decided against:** Putting the seeded DB in a shared writable fixture. The seed is read-only by convention. Any test that needs to write data uses the function-scoped `conn` fixture instead (fresh DB per test). This keeps isolation clean without needing complex transaction rollback strategies.

**Current limitation:** `seeded_conn` is largely underused — most tests still use `conn` because they need to write. The seed infrastructure is in place but not yet widely adopted. See `docs/testing/notes-test-infrastructure-alternatives.md` for the plan to address this.

---

### `tests/support/test_seed_db.py` — smoke tests for the seed

**Decision:** Add dedicated smoke tests that verify the seed populated correctly.

**Why:** If `seed_session_db()` silently fails or a schema change breaks it, every test that depends on seeded data will fail with misleading errors. The smoke tests catch seed failures at the source. They also document exactly what the seed is expected to contain.

---

### `tests/support/backtesting.py` — factory helpers

**Decision:** Add `make_backtest_result()` and `make_backtest_leaderboard_entry()` factory functions with keyword overrides.

**Why:** Constructing a `BacktestResult` or `BacktestLeaderboardEntry` required filling in 15–20 fields, most of which had no relevance to the test being written. The factory sets sensible defaults (zero returns, empty metrics) and lets callers override only what matters. Tests became a fraction of their original length and read as intent rather than noise.

The same principle applies to `insert_test_sleeve()` in `tests/support/sleeves.py`.

---

### `tests/conftest.py` — `seeded_conn` fixture

**Decision:** Add a session-scoped `seeded_conn` fixture alongside the existing function-scoped `conn`.

**Why:** The root conftest is the single place where infrastructure fixtures live. Putting `seeded_conn` here means it is available everywhere without imports. Using `tmp_path_factory` (rather than `tmp_path`) gives it session scope that is safe under pytest-xdist, where each worker gets its own isolated temp directory.

---

### Removing duplicate `conn` fixtures

**Decision:** Delete the locally-defined `conn` fixtures from `test_queries.py` (analysis) and `test_daily_report.py`.

**Why:** These local definitions were identical to the root conftest version. Their presence silently overrode the root fixture with no behavioral difference. They also carried unused imports (`Path`, `SQLiteBackend`, `get_backend`, etc.) that were left over from an earlier era when each file bootstrapped its own DB. Removing them reduces the surface area and ensures the root conftest is the single source of truth.

---

### `sleeve_env` and `rotation_sleeve_env` fixtures in `test_runtime_sleeve_mode.py`

**Decision:** Extract the repeated account/sleeve/snapshot/assignment setup into function-scoped fixtures returning `SimpleNamespace`.

**Why:** Seven of the eight tests in this file started with an identical or near-identical 10–15 line block creating the same entities. The fixture expresses *what the test environment looks like* in one place. Test bodies then express only *what is different about this scenario*.

`SimpleNamespace` was chosen over a typed dataclass because it is zero-boilerplate and the fixture is internal to the file. If these fixtures move to a conftest (see alternatives doc), a typed return type would become more valuable.

The eighth test (stale snapshot) was intentionally not converted to use `sleeve_env`, because it requires a snapshot timestamped in the past to trigger the stale-snapshot kill switch. Using the fixture (which inserts a recent snapshot) would defeat the test's purpose.

---

### `account_id` and `sleeve_id` fixtures in `test_sleeve_repositories.py`

**Decision:** Convert module-level helper functions `_account_id(conn, name)` and `_sleeve_id(conn, account_id, name)` into `@pytest.fixture` functions.

**Why:** The helpers were already close to fixtures — they took `conn` and returned an ID. Converting them removes the need for explicit `conn` passing in test bodies and integrates with pytest's injection system. Test methods that previously started with:

```python
account_id = _account_id(conn, "sleeve_orders_a")
sleeve_id = _sleeve_id(conn, account_id, "fills")
```

now accept `account_id` and `sleeve_id` as parameters directly. The fixture system handles the dependency chain (`sleeve_id` depends on `account_id` which depends on `conn`).

One subtle issue surfaced during this refactor: the fixture creates a sleeve named `"core"` (the default in `insert_test_sleeve`), but the existing test was asserting `row["name"] == "alpha"`. The assertion was updated to match the fixture's actual output.

---

### `report_env` fixture in `test_daily_report.py`

**Decision:** Add a function-scoped fixture that creates a standard account and sleeve, returned as a `SimpleNamespace`.

**Why:** Five of the eight tests in this file started with `insert_repository_account(...)` followed by `_insert_sleeve(...)`. The fixture collapses this to one parameter. The `_insert_sleeve` module-level helper was removed since it was only ever called in the fixture path.

---

### `base_account` fixture and parametrize consolidation in `test_configure.py`

**Decision:** Add a `base_account(conn)` fixture and merge two standalone configure-rejection tests into a single parametrized test.

**Why:** Eight tests in this file started with `create_account(conn, "acct_something", "Trend", 3000.0, "SPY")`. These unique names were artifacts of an older pattern where all tests shared a DB — with function-scoped `conn` (fresh DB per test), names don't need to be unique. The fixture creates a single canonical `"acct"` and returns its name.

The two configure-rejection tests (`rejects_invalid_iv_rank_range`, `rejects_invalid_delta_bounds`) were merged into `test_configure_account_rejects_invalid_range` with `@pytest.mark.parametrize`. Adding a new invalid case is now a one-line table entry.

---

## State of the test suite after this work

- **1295 tests, all passing**
- **89.84% coverage**
- Layer check: clean
- Mypy: clean

The infrastructure improvements were applied to the sleeve-related files and `test_configure.py`. Many other test files on this branch (governance jobs, runtime jobs, broker reconciliation) follow older patterns and were not touched. The support modules (`tests/support/`) are the right place to build shared helpers as those files are addressed.

---

## Why `?mode=ro` is the right choice for `seeded_conn` (not just `PRAGMA query_only`)

`PRAGMA query_only = ON` is connection-level software enforcement. It blocks DML and DDL but — per the SQLite docs — COMMIT of an already-open transaction still executes, WAL checkpoints still run, and `sqlite3_db_readonly()` returns 0, not 1.

The URI `?mode=ro` flag is enforced at the VFS (OS) layer, which closes all three gaps. It is the correct solution regardless of journal mode.

### Why the "When NOT to Use mode=ro" advice doesn't apply here

A common caution is: *"Tests that need to create tables or insert seed data must use a read-write connection, not mode=ro."* That rule is satisfied by design in our two-phase approach:

- **Phase 1** opens a fully writable connection via `SQLiteBackend`, runs `ensure_db()` and `seed_session_db()`, then **closes** the connection.
- **Phase 2** re-opens the now-complete file with `?mode=ro` and yields it to tests.

The `?mode=ro` connection never sees any writes — setup is fully finished before it opens.

The second caution — *"use `:memory:` for transient tests"* — is also inapplicable. In-memory databases disappear when their last connection closes, making the two-phase seed-then-reopen pattern impossible. A temp file is required precisely because we need to close the write connection and reopen the file read-only. Function-scoped `conn` (fresh file per test) is the correct fixture for mutation tests; `seeded_conn` is a different concern.


---

## What to do next

See `docs/testing/notes-test-infrastructure-alternatives.md` for the recommended next steps (directory-level `conftest.py` files, deeper seeded DB use, builder pattern). The recommended order is A → B → C.
