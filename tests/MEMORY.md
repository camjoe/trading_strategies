# Test Layout Memory

This file records a few test-suite decisions that are easy to forget later.

## Why The Test Directories Have `__init__.py`

Several grouped test directories now contain duplicate basenames such as:

- `tests/trading/services/accounts/test_queries.py`
- `tests/trading/services/analysis/test_queries.py`

Without package markers, pytest may import those files as top-level modules with
the same name, which causes import-file-mismatch errors during broader suite
collection.

We added `__init__.py` files under grouped test directories like:

- `tests/trading/`
- `tests/trading/services/`
- `tests/trading/backtesting/`

and their package subdirectories so pytest collects them as package-qualified
modules instead of unrelated top-level `test_*.py` modules.

The `__init__.py` files contain short test-oriented docstrings only. They are
not testing anything themselves. The docstrings are there just to make the file
purpose obvious when someone opens the directory.

## How Database Test Isolation Works

The main DB isolation fixture is in [tests/conftest.py](./conftest.py).

The `conn` fixture does this for each test that requests it:

1. stores the original active database backend
2. switches the active backend to `SQLiteBackend(tmp_path / "paper_trading.db")`
3. calls `ensure_db()` to initialize that temporary database
4. yields the temporary connection to the test
5. closes the connection in `finally`
6. restores the original backend in `finally`

This means the test is operating on a temporary SQLite file created under
pytest's per-test temporary directory, not the normal application database.

## Why We Know Test Data Is Cleaned Up

We rely on two cleanup mechanisms:

- fixture teardown closes the temporary connection and restores the original
  backend
- pytest `tmp_path` directories are temporary test artifacts, so the inserted
  rows live only in the per-test SQLite file

So the inserted data is not being deleted from the real application DB later;
it is written into an isolated temporary DB file that exists only for that test.

## Why We Know We Are Not Removing Real Data

For tests that use the `conn` fixture, the active backend is swapped before the
test performs any DB work. That means inserts, updates, and deletes go to the
temporary SQLite database, not the normal configured DB path.

Some tests use their own explicit backend fixture instead of `conn`, but the
safe pattern is the same:

- create a `SQLiteBackend(tmp_path / "...")`
- call `set_backend(...)`
- restore the original backend in teardown

The important rule is:

- tests that mutate DB state should use `conn` or another explicit tmp-path
  backend fixture before calling `ensure_db()` or other DB-writing flows

If a future test writes to the DB without first swapping to a temporary backend,
that would be a real safety problem and should be fixed immediately.
