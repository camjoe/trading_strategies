import pytest

from trading.models import AccountConfig
from trading.services.accounts import (
    create_account,
    find_account,
    get_account,
    list_account_names,
    list_account_records,
)
from tests.support.seed.db import ACCT_TREND


class TestAccountQueries:
    # Reads against pre-seeded accounts — no writes, seeded_conn safe.
    def test_get_account_not_found_raises(self, seeded_conn) -> None:
        with pytest.raises(ValueError, match="Account 'missing' not found"):
            get_account(seeded_conn, "missing")

    def test_find_account_strips_whitespace_and_returns_row(self, seeded_conn) -> None:
        account = find_account(seeded_conn, f"  {ACCT_TREND}  ")

        assert account is not None
        assert account["name"] == ACCT_TREND
        assert find_account(seeded_conn, "no_such_account") is None

    # Exact-list assertion on a known set — uses isolated conn to avoid noise
    # from the shared seeded DB.
    def test_list_account_records_returns_all_accounts(self, conn) -> None:
        create_account(conn, "acct_managed", "Trend", 1000.0, "SPY")
        create_account(
            conn,
            "acct_local",
            "Trend",
            1000.0,
            "SPY",
            config=AccountConfig(account_kind="local"),
        )
        rows = list_account_records(conn)
        names = [row["name"] for row in rows]

        assert names == ["acct_local", "acct_managed"]
        assert list_account_names(conn) == ["acct_local", "acct_managed"]
