from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from trading.backtesting.services.execution_service import run_backtest


class _Result:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


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
        run_backtest(
            conn=object(),
            cfg=cfg,
            get_account_fn=lambda _conn, _name: {"benchmark_ticker": "SPY", "id": 1, "initial_cash": 1000.0},
            resolve_backtest_dates_fn=lambda _s, _e, _l: (date(2026, 1, 1), date(2026, 1, 3)),
            warnings_for_config_fn=lambda _account, _allow: [],
            resolve_universe_fn=lambda _cfg, _start, _end: (["AAPL"], {"2026-01": ["AAPL"]}, ["AAPL"], []),
            fetch_close_history_fn=lambda _tickers, _start, _end: pd.DataFrame({"AAPL": [100.0, 101.0]}, index=short_index),
            fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0, 101.0]),
            row_expect_str_fn=lambda row, key: str(row[key]),
            row_expect_int_fn=lambda row, key: int(row[key]),
            row_expect_float_fn=lambda row, key: float(row[key]),
            resolve_active_strategy_fn=lambda _account: "trend",
            resolve_strategy_fn=lambda _name: SimpleNamespace(required_features=()),
            get_feature_provider_fn=lambda: None,
            insert_run_fn=lambda *_args, **_kwargs: 1,
            compute_market_value_fn=lambda _positions, _prices: 0.0,
            compute_unrealized_pnl_fn=lambda _positions, _avg, _marks: 0.0,
            update_on_buy_fn=lambda *_args, **_kwargs: 0.0,
            update_on_sell_fn=lambda *_args, **_kwargs: (0.0, 0.0),
            insert_trade_fn=lambda *_args, **_kwargs: None,
            insert_snapshot_fn=lambda *_args, **_kwargs: None,
            resolve_signal_fn=lambda *_args, **_kwargs: "hold",
            benchmark_return_pct_fn=lambda _series, _cash: 0.0,
            max_drawdown_pct_fn=lambda _curve: 0.0,
            backtest_result_cls=_Result,
        )


def test_execution_service_returns_result_for_hold_only_run() -> None:
    cfg = _base_cfg()
    idx = pd.date_range("2026-01-01", periods=3, freq="B")

    result = run_backtest(
        conn=SimpleNamespace(commit=lambda: None),
        cfg=cfg,
        get_account_fn=lambda _conn, _name: {"benchmark_ticker": "SPY", "id": 1, "initial_cash": 1000.0},
        resolve_backtest_dates_fn=lambda _s, _e, _l: (date(2026, 1, 1), date(2026, 1, 3)),
        warnings_for_config_fn=lambda _account, _allow: ["w1"],
        resolve_universe_fn=lambda _cfg, _start, _end: (["AAPL"], {"2026-01": ["AAPL"]}, ["AAPL"], []),
        fetch_close_history_fn=lambda _tickers, _start, _end: pd.DataFrame({"AAPL": [100.0, 101.0, 102.0]}, index=idx),
        fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0, 101.0, 102.0], index=idx),
        row_expect_str_fn=lambda row, key: str(row[key]),
        row_expect_int_fn=lambda row, key: int(row[key]),
        row_expect_float_fn=lambda row, key: float(row[key]),
        resolve_active_strategy_fn=lambda _account: "trend",
        resolve_strategy_fn=lambda _name: SimpleNamespace(required_features=()),
        get_feature_provider_fn=lambda: None,
        insert_run_fn=lambda *_args, **_kwargs: 77,
        compute_market_value_fn=lambda _positions, _prices: 0.0,
        compute_unrealized_pnl_fn=lambda _positions, _avg, _marks: 0.0,
        update_on_buy_fn=lambda *_args, **_kwargs: 0.0,
        update_on_sell_fn=lambda *_args, **_kwargs: (0.0, 0.0),
        insert_trade_fn=lambda *_args, **_kwargs: None,
        insert_snapshot_fn=lambda *_args, **_kwargs: None,
        resolve_signal_fn=lambda *_args, **_kwargs: "hold",
        benchmark_return_pct_fn=lambda _series, _cash: 1.0,
        max_drawdown_pct_fn=lambda _curve: -2.0,
        backtest_result_cls=_Result,
    )

    assert result.run_id == 77
    assert result.trade_count == 0
    assert result.max_drawdown_pct == -2.0
    assert result.sharpe_ratio is None
    assert result.win_rate_pct is None
