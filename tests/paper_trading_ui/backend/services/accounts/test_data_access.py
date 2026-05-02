from __future__ import annotations

from paper_trading_ui.backend.services.accounts import data_access as account_data_access


def test_fetch_visible_account_rows_excludes_manual_only_account(conn, create_account_row) -> None:
    create_account_row("acct_one")
    create_account_row("acct_local", account_kind="local")
    create_account_row("acct_manual", account_kind="manual_only")
    create_account_row("acct_two")

    rows = account_data_access.fetch_visible_account_rows(conn)
    names = [str(row["name"]) for row in rows]
    assert names == ["acct_local", "acct_one", "acct_two"]
