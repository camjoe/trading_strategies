import pytest

from trading.models import AccountConfig
from trading.services.accounts import (
    create_account,
    find_account,
    get_account,
    list_account_names,
    list_account_records,
)


class TestAccountQueries:
    def test_get_account_not_found_raises(self, conn) -> None:
        with pytest.raises(ValueError, match="Account 'missing' not found"):
            get_account(conn, "missing")

    def test_find_account_strips_name_and_returns_optional_row(self, conn) -> None:
        create_account(conn, "acct_lookup", "Trend", 1000.0, "SPY")

        account = find_account(conn, "  acct_lookup  ")

        assert account is not None
        assert account["name"] == "acct_lookup"
        assert find_account(conn, "missing") is None

    def test_list_account_records_normalizes_account_kind_filters(self, conn) -> None:
        create_account(conn, "acct_managed", "Trend", 1000.0, "SPY")
        create_account(
            conn,
            "acct_local",
            "Trend",
            1000.0,
            "SPY",
            config=AccountConfig(account_kind="local"),
        )
        rows = list_account_records(conn, account_kinds=(" Local ", "managed"))
        names = [row["name"] for row in rows]

        assert names == ["acct_local", "acct_managed"]
        assert list_account_names(conn, account_kinds=("managed",)) == ["acct_managed"]
