from __future__ import annotations

import pytest

import trading.backtesting.services.leaderboard_service as leaderboard_service


class _Row(dict):
    def __getitem__(self, key):
        return super().__getitem__(key)


def test_leaderboard_service_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="limit must be > 0"):
        leaderboard_service.fetch_backtest_leaderboard_entries(
            conn=object(),
            limit=0,
            account_name=None,
            strategy=None,
            fetch_benchmark_close_fn=lambda *_args, **_kwargs: None,
        )


def test_leaderboard_service_returns_sorted_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        _Row(
            run_id=1,
            run_name="r1",
            start_date="2026-01-01",
            end_date="2026-01-31",
            created_at="2026-02-01T00:00:00Z",
            account_name="acct",
            strategy="trend",
            benchmark_ticker="SPY",
            initial_cash=1000.0,
            starting_equity=1000.0,
            ending_equity=1050.0,
            trade_count=5,
        ),
        _Row(
            run_id=2,
            run_name="r2",
            start_date="2026-01-01",
            end_date="2026-01-31",
            created_at="2026-02-01T00:00:00Z",
            account_name="acct",
            strategy="mean_reversion",
            benchmark_ticker="SPY",
            initial_cash=1000.0,
            starting_equity=1000.0,
            ending_equity=1100.0,
            trade_count=4,
        ),
    ]

    monkeypatch.setattr(leaderboard_service, "fetch_leaderboard_rows", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(
        leaderboard_service,
        "fetch_equity_rows",
        lambda *_args, **_kwargs: [_Row(equity=1000.0), _Row(equity=1100.0)],
    )
    monkeypatch.setattr(
        leaderboard_service,
        "fetch_trade_rows",
        lambda *_args, **_kwargs: [
            _Row(ticker="AAPL", side="buy", qty=1.0, price=100.0, fee=0.0),
            _Row(ticker="AAPL", side="sell", qty=1.0, price=110.0, fee=0.0),
        ],
    )

    entries = leaderboard_service.fetch_backtest_leaderboard_entries(
        conn=object(),
        limit=10,
        account_name=None,
        strategy=None,
        fetch_benchmark_close_fn=lambda _ticker, _start, _end: [100.0, 101.0],
    )

    assert len(entries) == 2
    assert entries[0][0].run_id == 2
    assert entries[1][0].run_id == 1
    assert entries[0][0].win_rate_pct == pytest.approx(100.0)


def test_leaderboard_service_skips_rows_with_invalid_equity(monkeypatch: pytest.MonkeyPatch) -> None:
    bad_rows = [
        _Row(
            run_id=1,
            run_name="r1",
            start_date="2026-01-01",
            end_date="2026-01-31",
            created_at="2026-02-01T00:00:00Z",
            account_name="acct",
            strategy="trend",
            benchmark_ticker="SPY",
            initial_cash=1000.0,
            starting_equity=0.0,
            ending_equity=1100.0,
            trade_count=1,
        )
    ]

    monkeypatch.setattr(leaderboard_service, "fetch_leaderboard_rows", lambda *_args, **_kwargs: bad_rows)
    monkeypatch.setattr(leaderboard_service, "fetch_equity_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(leaderboard_service, "fetch_trade_rows", lambda *_args, **_kwargs: [])

    entries = leaderboard_service.fetch_backtest_leaderboard_entries(
        conn=object(),
        limit=10,
        account_name=None,
        strategy=None,
        fetch_benchmark_close_fn=lambda _ticker, _start, _end: [100.0, 101.0],
    )

    assert entries == []
