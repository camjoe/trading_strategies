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
            get_account_fn=lambda _conn, _name: {"benchmark_ticker": "SPY", "id": 1, "initial_cash": 1000.0},
            resolve_backtest_dates_fn=lambda _s, _e, _l: (date(2026, 1, 1), date(2026, 1, 3)),
            warnings_for_config_fn=lambda _account, _allow: [],
            resolve_universe_fn=lambda _cfg, _start, _end: (["AAPL"], {"2026-01": ["AAPL"]}, ["AAPL"], []),
            fetch_close_history_fn=lambda _tickers, _start, _end: pd.DataFrame({"AAPL": [100.0, 101.0]}, index=short_index),
            fetch_benchmark_close_fn=lambda _ticker, _start, _end: pd.Series([100.0, 101.0]),
            insert_run_fn=lambda *_args, **_kwargs: 1,
            insert_trade_fn=lambda *_args, **_kwargs: None,
            insert_snapshot_fn=lambda *_args, **_kwargs: None,
        )


def test_execution_service_returns_result_for_hold_only_run() -> None:
    cfg = _base_cfg()
    idx = pd.date_range("2026-01-01", periods=3, freq="B")

    with patch.object(execution_service, "resolve_active_strategy", lambda _account: "trend"), patch.object(
        execution_service,
        "resolve_strategy",
        lambda _name: SimpleNamespace(required_features=()),
    ), patch.object(
        execution_service,
        "benchmark_return_pct",
        lambda _series, _cash: 1.0,
    ), patch.object(
        execution_service,
        "max_drawdown_pct",
        lambda _curve: -2.0,
    ):
        result = execution_service.run_backtest(
            conn=SimpleNamespace(commit=lambda: None),
            cfg=cfg,
            get_account_fn=lambda _conn, _name: {"benchmark_ticker": "SPY", "id": 1, "initial_cash": 1000.0},
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
        )

    assert result.run_id == 77
    assert result.trade_count == 0
    assert result.max_drawdown_pct == -2.0
    assert result.sharpe_ratio is None
    assert result.win_rate_pct is None
