"""Conftest for the runtime_throttle service test suite.

Tests in this suite verify throttle enforcement logic by injecting
``MagicMock`` callables for settings-fetching and trade-counting.  The real DB
is not queried during enforcement checks — ``conn`` is passed through to
satisfy the function signature but the injected mocks short-circuit all
actual queries.  No suite-level DB fixture is needed here.
"""
