from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

import trading.backtesting.services.execution_service as execution_service


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
            fetch_close_history_fn=lambda _tickers, _start, _end: pd.DataFrame(
                {"AAPL": [100.0, 101.0]}, index=short_index
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
            fetch_close_history_fn=lambda _tickers, _start, _end: pd.DataFrame(
                {"AAPL": [100.0, 101.0, 102.0]},
                index=idx,
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
            lambda name: (resolved.append(name), SimpleNamespace(required_features=(), strategy_id=name, default_params={}))[1],
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
            fetch_close_history_fn=lambda _tickers, _start, _end: pd.DataFrame(
                {"AAPL": [100.0, 101.0, 102.0]}, index=idx
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
):
    """Run a minimal backtest with all I/O patched; returns BacktestResult."""
    if account is None:
        account = {"benchmark_ticker": "SPY", "id": 1, "initial_cash": 1000.0, "strategy": "trend"}
    kwargs = dict(
        conn=SimpleNamespace(commit=lambda: None),
        cfg=_base_cfg(),
        get_account_fn=lambda _conn, _name: account,
        resolve_backtest_dates_fn=lambda _s, _e, _l: (date(2026, 1, 1), date(2026, 1, 3)),
        warnings_for_config_fn=lambda _account, _allow: [],
        resolve_universe_fn=lambda _cfg, _start, _end: (["AAPL"], {"2026-01": ["AAPL"]}, ["AAPL"], []),
        fetch_close_history_fn=lambda _tickers, _start, _end: pd.DataFrame(close_data, index=idx),
        fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0] * len(idx), index=idx),
        insert_run_fn=lambda *_args, **_kwargs: 1,
        insert_trade_fn=lambda *_args, **_kwargs: None,
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


def test_execution_service_buy_skip_when_required_exceeds_cash() -> None:
    """Buy signal is ignored when required cost exceeds available cash (line 155)."""
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    result = _patched_run_backtest(
        idx,
        {"AAPL": [100.0, 100.0, 100.0]},
        lambda *_args, **_kwargs: "buy",
        # 1000 shares × $100 = $100 000, far exceeds the $1 000 starting cash.
        choose_buy_qty_fn=lambda *_args, **_kwargs: 1000,
    )
    assert result.trade_count == 0


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
