from __future__ import annotations

from paper_trading_ui.backend.config import TEST_BACKTEST_ACCOUNT_NAME
from paper_trading_ui.backend.services.accounts import data_access as account_data_access


def test_fetch_visible_account_rows_excludes_shadow_account(conn, create_test_account) -> None:
    create_test_account("acct_one")
    create_test_account("acct_local", account_kind="local")
    create_test_account(TEST_BACKTEST_ACCOUNT_NAME, account_kind="test_shadow")
    create_test_account("acct_two")

    rows = account_data_access.fetch_visible_account_rows(conn)
    names = [str(row["name"]) for row in rows]
    assert names == ["acct_local", "acct_one", "acct_two"]
