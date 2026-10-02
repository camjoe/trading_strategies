from __future__ import annotations

from decimal import Decimal

from paper_trading_web.backend.services.accounts import data_access as account_data_access

from trading.models.portfolio import EquitySnapshotRecord


def test_fetch_visible_account_rows_returns_all_accounts(conn, create_account_row) -> None:
    create_account_row("acct_one")
    create_account_row("acct_three")
    create_account_row("acct_two")

    rows = account_data_access.fetch_visible_account_rows(conn)
    names = [str(row["name"]) for row in rows]
    assert names == ["acct_one", "acct_three", "acct_two"]


def test_build_snapshot_payload_maps_record_fields_to_camelcase() -> None:
    snapshot = EquitySnapshotRecord(
        id=1,
        account_id=2,
        book_id=None,
        snapshot_time="2026-01-02T16:00:00Z",
        cash=Decimal("1000"),
        market_value=Decimal("500"),
        equity=Decimal("1500"),
        realized_pnl=Decimal("25"),
        unrealized_pnl=Decimal("-10"),
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
    assert all(type(value) is float for key, value in payload.items() if key != "time")


def test_build_trade_payload_renders_decimal_amounts_as_float() -> None:
    trade: dict[str, object] = {
        "book_id": 3,
        "ticker": "AAPL",
        "side": "buy",
        "qty": Decimal("1.5"),
        "price": Decimal("171.5272"),
        "fee": Decimal("1"),
        "trade_time": "2026-01-02T16:00:00Z",
        "note": "order=1",
    }

    payload = account_data_access.build_trade_payload(trade, book_names={3: "default"})

    assert payload["bookName"] == "default"
    assert (payload["qty"], payload["price"], payload["fee"]) == (1.5, 171.5272, 1.0)
    assert all(type(payload[key]) is float for key in ("qty", "price", "fee"))
