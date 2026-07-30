from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

import trading.backtesting.services.execution_service as execution_service
from tests.support.backtesting import bars_from_closes


def _base_cfg() -> SimpleNamespace:
    return SimpleNamespace(
        account_name="acct",
        start="2026-01-01",
        end="2026-01-03",
        lookback_months=None,
        allow_approximate_leaps=False,
        slippage_bps=0.0,
        fee_per_trade=0.0,
    )


def test_execution_service_rejects_short_history() -> None:
    cfg = _base_cfg()
    short_index = pd.date_range("2026-01-01", periods=2, freq="B")

    with pytest.raises(ValueError, match="Need at least 3 trading days"):
        execution_service.run_backtest(
            conn=object(),
            cfg=cfg,
            get_account_fn=lambda _conn, _name: {
                "benchmark_ticker": "SPY",
                "id": 1,
                "initial_cash": 1000.0,
                "strategy": "trend",
            },
            resolve_backtest_dates_fn=lambda _s, _e, _l: (date(2026, 1, 1), date(2026, 1, 3)),
            warnings_for_config_fn=lambda _account, _allow: [],
            resolve_universe_fn=lambda _cfg, _start, _end: (["AAPL"], {"2026-01": ["AAPL"]}, ["AAPL"], []),
            fetch_bar_history_fn=lambda _tickers, _start, _end: bars_from_closes(
                pd.DataFrame({"AAPL": [100.0, 101.0]}, index=short_index)
            ),
            fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0, 101.0]),
            insert_run_fn=lambda *_args, **_kwargs: 1,
            insert_trade_fn=lambda *_args, **_kwargs: None,
            insert_snapshot_fn=lambda *_args, **_kwargs: None,
            get_default_book_fn=lambda _conn, *, account_id: None,
        )


def test_execution_service_returns_result_for_hold_only_run() -> None:
    cfg = _base_cfg()
    idx = pd.date_range("2026-01-01", periods=3, freq="B")

    with (
        patch.object(execution_service, "active_strategy_for_account", lambda _conn, _account_id: "trend"),
        patch.object(
            execution_service,
            "resolve_strategy",
            lambda _name: SimpleNamespace(required_features=(), strategy_id="trend", default_params={}),
        ),
        patch.object(
            execution_service,
            "benchmark_return_pct",
            lambda _series, _cash: 1.0,
        ),
        patch.object(
            execution_service,
            "max_drawdown_pct",
            lambda _curve: -2.0,
        ),
    ):
        result = execution_service.run_backtest(
            conn=SimpleNamespace(commit=lambda: None),
            cfg=cfg,
            get_account_fn=lambda _conn, _name: {
                "benchmark_ticker": "SPY",
                "id": 1,
                "initial_cash": 1000.0,
                "strategy": "trend",
            },
            resolve_backtest_dates_fn=lambda _s, _e, _l: (date(2026, 1, 1), date(2026, 1, 3)),
            warnings_for_config_fn=lambda _account, _allow: ["w1"],
            resolve_universe_fn=lambda _cfg, _start, _end: (["AAPL"], {"2026-01": ["AAPL"]}, ["AAPL"], []),
            fetch_bar_history_fn=lambda _tickers, _start, _end: bars_from_closes(
                pd.DataFrame({"AAPL": [100.0, 101.0, 102.0]}, index=idx)
            ),
            fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0, 101.0, 102.0], index=idx),
            insert_run_fn=lambda *_args, **_kwargs: 77,
            insert_trade_fn=lambda *_args, **_kwargs: None,
            insert_snapshot_fn=lambda *_args, **_kwargs: None,
            get_default_book_fn=lambda _conn, *, account_id: None,
        )

    assert result.run_id == 77
    assert result.trade_count == 0
    assert result.max_drawdown_pct == -2.0
    assert result.sharpe_ratio is None
    assert result.win_rate_pct is None


def test_execution_service_strategy_override_bypasses_active_strategy() -> None:
    cfg = _base_cfg()
    cfg.strategy = "  meanrev  "  # whitespace-trimmed override
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    resolved: list[str] = []

    def _active_should_not_run(_conn, _account_id, *, fallback):  # pragma: no cover - must not be called
        raise AssertionError("active_strategy_for_account must not run when strategy override is set")

    with (
        patch.object(execution_service, "active_strategy_for_account", _active_should_not_run),
        patch.object(
            execution_service,
            "resolve_strategy",
            lambda name: (
                resolved.append(name),
                SimpleNamespace(required_features=(), strategy_id=name, default_params={}),
            )[1],
        ),
        patch.object(execution_service, "benchmark_return_pct", lambda _series, _cash: 1.0),
        patch.object(execution_service, "max_drawdown_pct", lambda _curve: -2.0),
    ):
        result = execution_service.run_backtest(
            conn=SimpleNamespace(commit=lambda: None),
            cfg=cfg,
            get_account_fn=lambda _conn, _name: {
                "benchmark_ticker": "SPY",
                "id": 1,
                "initial_cash": 1000.0,
                "strategy": "trend",
            },
            resolve_backtest_dates_fn=lambda _s, _e, _l: (date(2026, 1, 1), date(2026, 1, 3)),
            warnings_for_config_fn=lambda _account, _allow: [],
            resolve_universe_fn=lambda _cfg, _start, _end: (["AAPL"], {"2026-01": ["AAPL"]}, ["AAPL"], []),
            fetch_bar_history_fn=lambda _tickers, _start, _end: bars_from_closes(
                pd.DataFrame({"AAPL": [100.0, 101.0, 102.0]}, index=idx)
            ),
            fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0, 101.0, 102.0], index=idx),
            insert_run_fn=lambda _conn, _account_id, strategy_id, *_args, **_kwargs: (
                resolved.append(f"fk:{strategy_id}"),
                88,
            )[1],
            insert_trade_fn=lambda *_args, **_kwargs: None,
            insert_snapshot_fn=lambda *_args, **_kwargs: None,
            get_default_book_fn=lambda _conn, *, account_id: None,
        )

    assert result.run_id == 88
    # The override (trimmed) drove strategy resolution and the persisted FK.
    assert resolved == ["meanrev", "fk:meanrev"]


# ---------------------------------------------------------------------------
# _row_optional_float unit tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Buy-path skip guards (require patching resolve_signal to return "buy")
# ---------------------------------------------------------------------------


def _patched_run_backtest(
    idx: pd.DatetimeIndex,
    close_data: dict,
    resolve_signal_fn,
    choose_buy_qty_fn=None,
    account: dict | None = None,
    insert_trade_fn=None,
):
    """Run a minimal backtest with all I/O patched; returns BacktestResult.

    The universe is taken from ``close_data`` so multi-ticker bars — where cash
    has to be shared between simultaneous buy signals — can be exercised.
    """
    if account is None:
        account = {"benchmark_ticker": "SPY", "id": 1, "initial_cash": 1000.0, "strategy": "trend"}
    tickers = list(close_data)
    kwargs = dict(
        conn=SimpleNamespace(commit=lambda: None),
        cfg=_base_cfg(),
        get_account_fn=lambda _conn, _name: account,
        resolve_backtest_dates_fn=lambda _s, _e, _l: (date(2026, 1, 1), date(2026, 1, 3)),
        warnings_for_config_fn=lambda _account, _allow: [],
        resolve_universe_fn=lambda _cfg, _start, _end: (tickers, {"2026-01": tickers}, tickers, []),
        fetch_bar_history_fn=lambda _tickers, _start, _end: bars_from_closes(pd.DataFrame(close_data, index=idx)),
        fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0] * len(idx), index=idx),
        insert_run_fn=lambda *_args, **_kwargs: 1,
        insert_trade_fn=insert_trade_fn or (lambda *_args, **_kwargs: None),
        insert_snapshot_fn=lambda *_args, **_kwargs: None,
        get_default_book_fn=lambda _conn, *, account_id: None,
    )
    if choose_buy_qty_fn is not None:
        kwargs["choose_buy_qty_fn"] = choose_buy_qty_fn

    with (
        patch.object(execution_service, "active_strategy_for_account", lambda _conn, _account_id: "trend"),
        patch.object(
            execution_service,
            "resolve_strategy",
            lambda _name: SimpleNamespace(required_features=(), strategy_id="trend", default_params={}),
        ),
        patch.object(execution_service, "evaluate_signal", resolve_signal_fn),
        patch.object(execution_service, "benchmark_return_pct", lambda _series, _cash: 1.0),
        patch.object(execution_service, "max_drawdown_pct", lambda _curve: -2.0),
    ):
        return execution_service.run_backtest(**kwargs)


def test_execution_service_buy_skip_when_price_is_zero() -> None:
    """Buy signal is ignored when trade price is zero (line 135)."""
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    result = _patched_run_backtest(
        idx,
        {"AAPL": [0.0, 0.0, 0.0]},
        lambda *_args, **_kwargs: "buy",
    )
    assert result.trade_count == 0


def test_execution_service_buy_skip_when_qty_less_than_one() -> None:
    """Buy signal is ignored when choose_buy_qty returns zero (line 151).

    Also exercises _row_optional_float with a missing key (lines 29-31), since
    the account row does not contain 'trade_size_pct'.
    """
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    result = _patched_run_backtest(
        idx,
        {"AAPL": [100.0, 100.0, 100.0]},
        lambda *_args, **_kwargs: "buy",
        choose_buy_qty_fn=lambda *_args, **_kwargs: 0,
    )
    assert result.trade_count == 0


def test_execution_service_buy_is_scaled_down_when_required_exceeds_cash() -> None:
    """A request larger than cash is funded down to what cash affords, not dropped.

    Cash-constrained buys are partially filled rather than skipped, so the bar
    spends what it has instead of leaving it idle. ``choose_buy_qty`` already
    caps at available cash in production; this covers the guard behind it.
    """
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    result = _patched_run_backtest(
        idx,
        {"AAPL": [100.0, 100.0, 100.0]},
        lambda *_args, **_kwargs: "buy",
        # 1000 shares × $100 = $100 000, far exceeds the $1 000 starting cash.
        choose_buy_qty_fn=lambda *_args, **_kwargs: 1000,
    )
    assert result.trade_count == 1
    # $1 000 buys 9 shares at $100 plus slippage; never more than cash allows.
    assert result.ending_equity <= 1000.0


# ---------------------------------------------------------------------------
# Sell-path skip guard
# ---------------------------------------------------------------------------


def test_execution_service_sell_skip_when_price_is_zero() -> None:
    """Sell signal is ignored when trade price is zero after a prior buy (line 184)."""
    idx = pd.date_range("2026-01-01", periods=3, freq="B")

    # Day 1 → buy at 100.0; Day 2 → sell attempt at 0.0 (skipped).
    signals = iter(["buy", "sell"])

    result = _patched_run_backtest(
        idx,
        {"AAPL": [100.0, 100.0, 0.0]},
        lambda *_args, **_kwargs: next(signals, "hold"),
        choose_buy_qty_fn=lambda *_args, **_kwargs: 5,
    )
    # The buy on day 1 executed; the sell on day 2 was skipped.
    assert result.trade_count == 1


# ---------------------------------------------------------------------------
# Warm-up: history before the scoring window initializes indicators, but returns
# and trades are measured only from the window start.
# ---------------------------------------------------------------------------


def _run_with_warmup(*, warmup_months: int, scoring_start: date, end: date, idx, series: pd.Series):
    account = {"benchmark_ticker": "SPY", "id": 1, "initial_cash": 1000.0, "strategy": "trend"}
    cfg = SimpleNamespace(
        account_name="acct_warmup",
        tickers_file="t.txt",
        universe_history_dir=None,
        start=scoring_start.isoformat(),
        end=end.isoformat(),
        lookback_months=None,
        slippage_bps=0.0,
        fee_per_trade=0.0,
        run_name=None,
        allow_approximate_leaps=False,
        strategy="trend",
        purpose="standalone",
        param_override=None,
        warmup_months=warmup_months,
    )
    frame = pd.DataFrame({"AAPL": series})

    # Realistic fetch: return only the bars within the requested [start, end] range.
    def fetch_bars(_tickers, start, end_):
        return bars_from_closes(frame.loc[pd.Timestamp(start) : pd.Timestamp(end_)])

    return execution_service.run_backtest(
        SimpleNamespace(commit=lambda: None),
        cfg,
        get_account_fn=lambda _conn, _name: account,
        resolve_backtest_dates_fn=lambda _s, _e, _l: (scoring_start, end),
        warnings_for_config_fn=lambda _account, _allow: [],
        resolve_universe_fn=lambda _cfg, _start, _end: (["AAPL"], {}, ["AAPL"], []),
        fetch_bar_history_fn=fetch_bars,
        fetch_benchmark_close_fn=lambda _t, _s, _e: pd.Series([100.0] * len(idx), index=idx),
        insert_run_fn=lambda *_args, **_kwargs: 1,
        insert_trade_fn=lambda *_args, **_kwargs: None,
        insert_snapshot_fn=lambda *_args, **_kwargs: None,
        choose_buy_qty_fn=lambda *_args, **_kwargs: 2,
        get_default_book_fn=lambda _conn, *, account_id: None,
    )


def test_warmup_enables_signals_in_a_short_window() -> None:
    # A rising series over ~160 business days; the scoring window is only ~21 bars —
    # shorter than the trend strategy's 30-bar warm-up requirement.
    idx = pd.date_range("2026-01-01", periods=160, freq="B")
    series = pd.Series([50.0 + i for i in range(len(idx))], index=idx)
    scoring_start = idx[-21].date()
    end = idx[-1].date()

    cold = _run_with_warmup(warmup_months=0, scoring_start=scoring_start, end=end, idx=idx, series=series)
    warm = _run_with_warmup(warmup_months=3, scoring_start=scoring_start, end=end, idx=idx, series=series)

    # Without warm-up the strategy never accumulates enough history to signal → flat.
    assert cold.trade_count == 0
    assert cold.total_return_pct == 0.0
    # With warm-up it is warm at the window start and trades within the window.
    assert warm.trade_count > 0
    # Either way, the reported period is the scoring window, not the warm-up lead-in.
    assert cold.start_date == scoring_start.isoformat()
    assert warm.start_date == scoring_start.isoformat()


# ---------------------------------------------------------------------------
# Cash allocation across simultaneous buy signals
# ---------------------------------------------------------------------------


def _recorded_trades():
    trades: list[tuple[str, str, float]] = []

    def record(_conn, _run_id, _trade_time, ticker, side, qty, *_args, **_kwargs):
        trades.append((ticker, side, qty))

    return trades, record


def test_simultaneous_buys_share_cash_instead_of_funding_alphabetically() -> None:
    """Two equal buy signals, cash for one: both are funded, neither is preferred.

    Funding requests in iteration order would give AAAA its full position and
    ZZZZ nothing — an outcome decided by the alphabet rather than the strategy.
    """
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    trades, record = _recorded_trades()
    _patched_run_backtest(
        idx,
        {"AAAA": [100.0, 100.0, 100.0], "ZZZZ": [100.0, 100.0, 100.0]},
        lambda *_args, **_kwargs: "buy",
        # Each ticker asks for the entire $1 000 of starting cash.
        choose_buy_qty_fn=lambda *_args, **_kwargs: 10,
        insert_trade_fn=record,
    )

    buys = {ticker: qty for ticker, side, qty in trades if side == "buy"}
    assert set(buys) == {"AAAA", "ZZZZ"}
    assert buys["AAAA"] == buys["ZZZZ"]


def test_buy_ordering_does_not_change_the_outcome() -> None:
    """The same signals must allocate identically whichever order they arrive in."""
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    forward, record_forward = _recorded_trades()
    _patched_run_backtest(
        idx,
        {"AAAA": [100.0, 100.0, 100.0], "ZZZZ": [50.0, 50.0, 50.0]},
        lambda *_args, **_kwargs: "buy",
        choose_buy_qty_fn=lambda _cash, price, *_args, **_kwargs: int(800 // price),
        insert_trade_fn=record_forward,
    )
    reverse, record_reverse = _recorded_trades()
    _patched_run_backtest(
        idx,
        {"ZZZZ": [50.0, 50.0, 50.0], "AAAA": [100.0, 100.0, 100.0]},
        lambda *_args, **_kwargs: "buy",
        choose_buy_qty_fn=lambda _cash, price, *_args, **_kwargs: int(800 // price),
        insert_trade_fn=record_reverse,
    )

    assert sorted(forward) == sorted(reverse)


def test_sell_proceeds_fund_the_same_bar_regardless_of_ticker_order() -> None:
    """A sell frees cash for every buy on the bar, not only later tickers.

    ZZZZ is sold and AAAA bought on the same bar; sorted iteration reaches AAAA
    first, so interleaving the two would have hidden ZZZZ's proceeds from it.
    """
    idx = pd.date_range("2026-01-01", periods=4, freq="B")
    trades, record = _recorded_trades()

    def scripted(_strategy, history, _params, _features=None):
        """Buy ZZZZ on the first bar, then swap into AAAA on every later bar.

        The two tickers are priced apart so the signal can tell them apart from
        the history alone — ``evaluate_signal`` is not given the ticker.
        """
        is_zzzz = float(history.iloc[-1]) < 75.0
        if len(history) <= 1:
            return "buy" if is_zzzz else "hold"
        return "sell" if is_zzzz else "buy"

    _patched_run_backtest(
        idx,
        {"AAAA": [100.0] * 4, "ZZZZ": [50.0] * 4},
        scripted,
        # Spend everything available, so AAAA is affordable only once ZZZZ has sold.
        choose_buy_qty_fn=lambda cash, price, *_args, **_kwargs: int(cash // price),
        insert_trade_fn=record,
    )

    assert ("ZZZZ", "buy", 20.0) in trades
    assert any(ticker == "ZZZZ" and side == "sell" for ticker, side, _qty in trades)
    assert any(ticker == "AAAA" and side == "buy" for ticker, side, _qty in trades)
