# Test Infrastructure Alternatives

This document evaluates three directions for improving the test infrastructure beyond what has already been implemented. Each section names the driving problem, describes the alternative, and discusses whether it should be combined with the others.

---

## A. Directory-level `conftest.py` files

### What problem drives this

**Fixtures are file-local.** Fixtures like `sleeve_env`, `rotation_sleeve_env`, and `report_env` are defined directly inside their respective test files. This works today, but it creates a growth trap: when a second or third test file in the same folder needs the same setup, the author either duplicates the fixture or imports it directly from another test file (an anti-pattern — test files aren't modules). The pattern looks fine now because the sleeve test suite is young, but it will silently accumulate duplication as coverage grows.

The current structure also makes it hard for a new contributor (or a returning author) to discover what setup is available within a given test subtree.

### What the alternative does

Pytest auto-discovers `conftest.py` at any directory level and makes all fixtures defined there available to every test in that subtree — no imports required. Moving `sleeve_env`, `rotation_sleeve_env`, `report_env`, `account_id`, `sleeve_id`, and similar fixtures into directory-level `conftest.py` files means:

- Any test in `tests/trading/services/sleeves/` gets `report_env` without touching imports.
- Any test in `tests/trading/repositories/` gets `account_id` and `sleeve_id` without touching imports.
- Adding a new fixture once in `conftest.py` benefits all current and future tests in that subtree automatically.

The `tests/support/` helpers (`insert_test_sleeve`, `make_backtest_result`, etc.) stay where they are — `conftest.py` is for pytest fixtures that wrap those helpers, not for the helpers themselves.

### Should this be combined with B or C

**Yes — A is foundational and should happen first regardless of which other alternatives are chosen.** B needs a reliable fixture layer to express read-only test groupings clearly. C (builders) would also surface through `conftest.py` fixtures. A has essentially no downside: it is a structural move, not a new pattern.

---

## B. Deeper seeded DB use

### What problem drives this

Two related problems:

**`seeded_conn` is underused.** The seed infrastructure (`tests/support/seed_db.py`, the `seeded_conn` fixture, named constants) was built, but the vast majority of tests still use the function-scoped `conn`, which initializes a fresh SQLite DB for every single test. The upfront investment in the seed isn't paying off yet.

**The read-only convention is unenforced.** Nothing stops a test from writing to `seeded_conn` and silently mutating the shared DB state, potentially causing flaky failures for other tests in the same xdist worker. The convention exists only in a comment.

There is also a performance angle: DB initialization (schema creation, seed population) runs once per `conn` invocation. With 1295 tests and a 4.5-minute test run, tests that only read — "does this query return the right shape for a known account?" — do not need a fresh DB each time.

### What the alternative does

Designate a class of tests as explicitly read-only. These tests accept `seeded_conn` instead of `conn` and promise not to write. A pytest marker (`@pytest.mark.uses_seeded_db`) can document the contract and could eventually enforce it via a plugin or fixture guard.

The seeded DB is initialized once per worker (already the case with `tmp_path_factory`) and reused across all tests that carry the marker. Read-heavy areas — query shape tests, reporting tests, analysis tests, leaderboard read tests — are the best candidates.

The enforcement question is important. One practical approach: a thin fixture wrapper that opens `seeded_conn` with SQLite's `query_only = ON` pragma for the duration of the test. Any accidental write attempt raises immediately with a clear message rather than silently corrupting shared state.

### Should this be combined with A or C

**B needs A first.** Without directory-level `conftest.py` files, the distinction between "this test takes `conn`" and "this test takes `seeded_conn`" is harder to reason about for an entire subtree. A `conftest.py` at the subtree level can document or enforce the default clearly.

B is independent of C. You can have read-only seeded tests without builders and vice versa.

---

## C. Builder / Object-Mother pattern

### What problem drives this

**The complexity of multi-entity setups.** Even with the fixtures added so far, the hardest tests to read are the ones that need a rich object graph: a sleeve with a strategy assignment, metric rows, a rotation decision, and a snapshot. Those setups are written as a sequence of raw repository calls — procedural, order-dependent, and verbose. Anyone reading the test has to mentally parse which entities are being wired together and why.

This is a different problem from the ones A and B solve. A solves discoverability. B solves reuse and performance. C solves *expressiveness at the point of complex setup*.

Consider the current worst offender — `rotation_sleeve_env` — which is 30+ lines of sequential inserts before the first assertion. If the rotation logic requires a new field tomorrow, every test that depends on this fixture may need updating even though the test itself is about rotation logic, not about what fields a sleeve has. The procedural approach also makes it hard to see at a glance what relationship between entities the test is actually exercising.

### What the alternative does

A builder (or "object mother") wraps the repository calls behind a composable interface:

```python
env = (
    SleeveFixture(conn)
    .with_strategy("trend", incumbent=True)
    .with_metric(date="2026-05-03", return_pct=1.2)
    .with_snapshot()
    .build()
)
```

`env.sleeve_id`, `env.account_id`, `env.strategy_name` are available on the result. The builder handles ordering, sets sensible defaults, and is the single place to update when the schema changes.

The "object mother" variant is simpler: named factory functions that return pre-built standard scenarios (`standard_rotation_env(conn)`, `stale_snapshot_env(conn)`). Less flexible than a builder, but much less code. Given the current scale, starting with named factory functions in `tests/support/` and graduating to a full builder only if scenarios multiply is the pragmatic path.

### Should this be combined with A or B

**A is a soft prerequisite.** Builders and factory functions in `tests/support/` surface naturally through fixtures in directory-level `conftest.py`. Without A, each test file has to manually wire the builder call itself — which just shifts where the boilerplate lives.

C does not conflict with B. A read-only seeded test can coexist with a fixture that uses a builder for its writable variant. They operate at different layers.

---

## Integration recommendation

These three are not mutually exclusive. The recommended order:

1. **A first** — move existing fixtures into directory-level `conftest.py` files. Low risk, no new patterns, pays dividends immediately.
2. **B alongside or shortly after A** — once the fixture layer is stable, mark and convert read-only tests to use `seeded_conn`. Add the `query_only` enforcement pragma. This addresses both the underuse problem and the unenforced convention at once.
3. **C later, selectively** — introduce named factory functions (object mother style) in `tests/support/` for the two or three most complex setup scenarios (rotation env, shadow evaluation env). Adopt a full builder only if the number of scenario variants justifies the abstraction cost.

A and B together solve the structural and isolation problems. C solves the expressiveness problem and is worth doing for the high-complexity setups regardless, but it should not block A and B.
