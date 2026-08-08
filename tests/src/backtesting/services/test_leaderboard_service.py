from __future__ import annotations

import pytest

import backtesting.services.leaderboard_service as leaderboard_service


class _Row(dict):
    def __getitem__(self, key):
        return super().__getitem__(key)


def _leaderboard_row(**overrides) -> _Row:
    base = dict(
        run_id=1,
        run_name="r1",
        start_date="2026-01-01",
        end_date="2026-01-31",
        created_at="2026-02-01T00:00:00Z",
        account_name="acct",
        strategy="trend",
        benchmark_return_pct=1.0,
        starting_equity=1000.0,
        ending_equity=1050.0,
        trade_count=5,
    )
    base.update(overrides)
    return _Row(**base)


def _stub_run_reads(monkeypatch: pytest.MonkeyPatch, *, snapshots, trades) -> None:
    monkeypatch.setattr(leaderboard_service, "fetch_backtest_report_snapshots", lambda *_a, **_kw: snapshots)
    monkeypatch.setattr(leaderboard_service, "fetch_backtest_report_trades", lambda *_a, **_kw: trades)


def test_leaderboard_service_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="limit must be > 0"):
        leaderboard_service.fetch_backtest_leaderboard_entries(
            conn=object(),
            limit=0,
            account_name=None,
            strategy=None,
        )


def test_leaderboard_service_returns_sorted_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        _leaderboard_row(run_id=1, strategy="trend", ending_equity=1050.0),
        _leaderboard_row(run_id=2, run_name="r2", strategy="mean_reversion", ending_equity=1100.0, trade_count=4),
    ]

    monkeypatch.setattr(leaderboard_service, "fetch_leaderboard_rows", lambda *_a, **_kw: rows)
    _stub_run_reads(
        monkeypatch,
        snapshots=[_Row(equity=1000.0), _Row(equity=1100.0)],
        trades=[
            _Row(ticker="AAPL", side="buy", qty=1.0, price=100.0, fee=0.0),
            _Row(ticker="AAPL", side="sell", qty=1.0, price=110.0, fee=0.0),
        ],
    )

    entries = leaderboard_service.fetch_backtest_leaderboard_entries(
        conn=object(),
        limit=10,
        account_name=None,
        strategy=None,
    )

    assert len(entries) == 2
    assert entries[0][0].run_id == 2
    assert entries[1][0].run_id == 1
    assert entries[0][0].win_rate_pct == pytest.approx(100.0)


def test_leaderboard_carries_the_stored_benchmark_and_derives_alpha(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1000 -> 1050 is +5%; the run's frozen benchmark is +1%, so alpha is +4%.
    monkeypatch.setattr(
        leaderboard_service,
        "fetch_leaderboard_rows",
        lambda *_a, **_kw: [_leaderboard_row(benchmark_return_pct=1.0)],
    )
    _stub_run_reads(monkeypatch, snapshots=[_Row(equity=1000.0), _Row(equity=1050.0)], trades=[])

    ((entry, _starting_equity),) = leaderboard_service.fetch_backtest_leaderboard_entries(
        conn=object(),
        limit=10,
        account_name=None,
        strategy=None,
    )

    assert entry.total_return_pct == pytest.approx(5.0)
    assert entry.benchmark_return_pct == pytest.approx(1.0)
    assert entry.alpha_pct == pytest.approx(4.0)


def test_leaderboard_reports_no_alpha_when_the_run_stored_no_benchmark(monkeypatch: pytest.MonkeyPatch) -> None:
    # Runs written before revision 0030, and runs whose benchmark had no history.
    monkeypatch.setattr(
        leaderboard_service,
        "fetch_leaderboard_rows",
        lambda *_a, **_kw: [_leaderboard_row(benchmark_return_pct=None)],
    )
    _stub_run_reads(monkeypatch, snapshots=[_Row(equity=1000.0), _Row(equity=1050.0)], trades=[])

    ((entry, _starting_equity),) = leaderboard_service.fetch_backtest_leaderboard_entries(
        conn=object(),
        limit=10,
        account_name=None,
        strategy=None,
    )

    assert entry.benchmark_return_pct is None
    assert entry.alpha_pct is None


def test_leaderboard_service_skips_rows_with_invalid_equity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        leaderboard_service,
        "fetch_leaderboard_rows",
        lambda *_a, **_kw: [_leaderboard_row(starting_equity=0.0, ending_equity=1100.0, trade_count=1)],
    )
    _stub_run_reads(monkeypatch, snapshots=[], trades=[])

    entries = leaderboard_service.fetch_backtest_leaderboard_entries(
        conn=object(),
        limit=10,
        account_name=None,
        strategy=None,
    )

    assert entries == []
