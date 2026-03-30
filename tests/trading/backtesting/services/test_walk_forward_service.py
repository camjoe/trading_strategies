from __future__ import annotations

from datetime import date

import pytest

from trading.backtesting.services.walk_forward_service import execute_walk_forward_backtest
from trading.models.backtesting import WalkForwardConfig


class _Result:
    def __init__(self, run_id: int, total_return_pct: float) -> None:
        self.run_id = run_id
        self.total_return_pct = total_return_pct


def _cfg() -> WalkForwardConfig:
    return WalkForwardConfig(
        account_name="acct",
        tickers_file="trading/config/trade_universe.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-31",
        lookback_months=None,
        test_months=1,
        step_months=1,
        slippage_bps=5.0,
        fee_per_trade=0.0,
        run_name_prefix="wf",
        allow_approximate_leaps=False,
    )


def test_walk_forward_service_builds_summary_and_run_names() -> None:
    seen_run_names: list[str | None] = []

    def fake_run_backtest(_conn, cfg):
        seen_run_names.append(cfg.run_name)
        i = len(seen_run_names)
        return _Result(run_id=100 + i, total_return_pct=float(i))

    summary = execute_walk_forward_backtest(
        conn=object(),
        cfg=_cfg(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        windows=[
            (date(2026, 1, 1), date(2026, 1, 31)),
            (date(2026, 2, 1), date(2026, 2, 28)),
            (date(2026, 3, 1), date(2026, 3, 31)),
        ],
        run_backtest_fn=fake_run_backtest,
    )

    assert seen_run_names == ["wf_wf_01", "wf_wf_02", "wf_wf_03"]
    assert summary.window_count == 3
    assert summary.run_ids == [101, 102, 103]
    assert summary.average_return_pct == 2.0
    assert summary.median_return_pct == 2.0
    assert summary.best_return_pct == 3.0
    assert summary.worst_return_pct == 1.0


def test_walk_forward_service_rejects_empty_windows() -> None:
    with pytest.raises(ValueError, match="No walk-forward windows generated"):
        execute_walk_forward_backtest(
            conn=object(),
            cfg=_cfg(),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            windows=[],
            run_backtest_fn=lambda _conn, _cfg: _Result(run_id=1, total_return_pct=1.0),
        )
