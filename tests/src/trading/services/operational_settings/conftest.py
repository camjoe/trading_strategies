"""Conftest for the operational_settings service test suite.

Settings tests (mutations/queries) follow a write-then-read pattern: each test
calls a ``set_*`` mutation before a ``fetch_*`` query to verify the persisted
result, or tests the empty-DB default with a fresh ``conn`` and no prior writes.
Throttle enforcement tests inject ``MagicMock`` callables for settings-fetching
and trade-counting, so the real DB is not queried during those checks.  Because
there is no shared pre-seeded state across tests, the root ``conn`` fixture
(function-scoped, fresh empty DB) is sufficient — no suite-level DB fixture is
needed here.
"""
