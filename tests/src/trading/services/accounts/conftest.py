import pytest

from trading.services.accounts import create_account


@pytest.fixture
def base_account(conn) -> str:
    """Plain account ready for configure/validation tests."""
    create_account(conn, "acct", "Trend", 3000.0, "SPY")
    return "acct"
