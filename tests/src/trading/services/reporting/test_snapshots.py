import pytest

from tests.support.books import ensure_default_book_id
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.accounts import create_account, get_account
from trading.services.reporting import show_snapshots, snapshot_account


def test_snapshot_account_inserts_and_defaults_time(conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    create_account(conn, "acct_snap", "Trend", 1000.0, "SPY")
    monkeypatch.setattr(
        "trading.services.reporting.snapshots.account_report",
        lambda _conn, _name, **_kwargs: (
            {
                "cash": 900.0,
                "market_value": 150.0,
                "equity": 1050.0,
                "realized_pnl": 20.0,
                "unrealized_pnl": 30.0,
            },
            {"AAPL": 1.0},
        ),
    )
    monkeypatch.setattr("trading.services.reporting.snapshots.utc_now_iso", lambda: "2099-01-01T00:00:00Z")

    snapshot_account(conn, "acct_snap", snapshot_time=None)
    assert "Snapshot saved." in capsys.readouterr().out

    account = get_account(conn, "acct_snap")
    row = conn.execute(
        """
        SELECT s.snapshot_time, s.equity
        FROM equity_snapshots s
        JOIN books b ON b.id = s.book_id
        WHERE b.account_id = ?
        """,
        (account["id"],),
    ).fetchone()
    assert row["snapshot_time"] == "2099-01-01T00:00:00Z"
    assert float(row["equity"]) == pytest.approx(1050.0)


def test_show_snapshots_handles_empty_and_rows(conn, capsys) -> None:
    create_account(conn, "acct_show", "Trend", 1000.0, "SPY")

    show_snapshots(conn, "acct_show", limit=5)
    assert "No snapshots found." in capsys.readouterr().out

    account = get_account(conn, "acct_show")
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=ensure_default_book_id(conn, int(account["id"])),
        snapshot_time="2026-03-01T00:00:00Z",
        cash=900.0,
        market_value=100.0,
        equity=1000.0,
        realized_pnl=10.0,
        unrealized_pnl=15.0,
    )

    show_snapshots(conn, "acct_show", limit=5)
    out = capsys.readouterr().out
    assert "Snapshot history (latest 5) for acct_show:" in out
    assert "equity=1000.00" in out
