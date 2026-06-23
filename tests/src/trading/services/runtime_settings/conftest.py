"""Conftest for the runtime_settings service test suite.

All tests in this suite follow a write-then-read pattern: each test calls a
``set_*`` mutation before calling a ``fetch_*`` query to verify the persisted
result, or tests the empty-DB default by using a fresh ``conn`` with no prior
writes.  Because there is no shared pre-seeded state across tests, the root
``conn`` fixture (function-scoped, fresh empty DB) is sufficient for all
cases — no suite-level DB fixture is needed here.
"""
