from __future__ import annotations

from paper_trading_web.backend.services.accounts import data_access as account_data_access
from trading.models.portfolio.equity_snapshot_record import EquitySnapshotRecord


def test_fetch_visible_account_rows_returns_managed_and_local_accounts(conn, create_account_row) -> None:
    create_account_row("acct_one")
    create_account_row("acct_local", account_kind="local")
    create_account_row("acct_two")

    rows = account_data_access.fetch_visible_account_rows(conn)
    names = [str(row["name"]) for row in rows]
    assert names == ["acct_local", "acct_one", "acct_two"]


def test_build_snapshot_payload_maps_record_fields_to_camelcase() -> None:
    snapshot = EquitySnapshotRecord(
        id=1,
        account_id=2,
        snapshot_time="2026-01-02T16:00:00Z",
        cash=1000.0,
        market_value=500.0,
        equity=1500.0,
        realized_pnl=25.0,
        unrealized_pnl=-10.0,
    )

    payload = account_data_access.build_snapshot_payload(snapshot)

    assert payload == {
        "time": "2026-01-02T16:00:00Z",
        "cash": 1000.0,
        "marketValue": 500.0,
        "equity": 1500.0,
        "realizedPnl": 25.0,
        "unrealizedPnl": -10.0,
    }
