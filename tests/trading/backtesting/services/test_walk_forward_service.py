from __future__ import annotations

from datetime import date

import pytest

from trading.backtesting.services.walk_forward_service import execute_walk_forward_backtest
from trading.backtesting.models import WalkForwardConfig


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
    persisted_groups: list[dict[str, object]] = []
    persisted_group_runs: list[dict[str, object]] = []

    def fake_run_backtest(_conn, cfg):
        seen_run_names.append(cfg.run_name)
        i = len(seen_run_names)
        return _Result(run_id=100 + i, total_return_pct=float(i))

    def fake_insert_group(_conn, **kwargs) -> int:
        persisted_groups.append(kwargs)
        return 77

    def fake_insert_group_run(_conn, **kwargs) -> None:
        persisted_group_runs.append(kwargs)

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
        insert_group_fn=fake_insert_group,
        insert_group_run_fn=fake_insert_group_run,
        grouping_key_factory=lambda: "wf-group-1",
        commit_fn=lambda _conn: None,
    )

    assert seen_run_names == ["wf_wf_01", "wf_wf_02", "wf_wf_03"]
    assert summary.window_count == 3
    assert summary.run_ids == [101, 102, 103]
    assert summary.average_return_pct == 2.0
    assert summary.median_return_pct == 2.0
    assert summary.best_return_pct == 3.0
    assert summary.worst_return_pct == 1.0
    assert persisted_groups == [
        {
            "primary_run_id": 101,
            "grouping_key": "wf-group-1",
            "run_name_prefix": "wf",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "test_months": 1,
            "step_months": 1,
            "window_count": 3,
            "average_return_pct": 2.0,
            "median_return_pct": 2.0,
            "best_return_pct": 3.0,
            "worst_return_pct": 1.0,
        }
    ]
    assert persisted_group_runs == [
        {
            "group_id": 77,
            "run_id": 101,
            "window_index": 1,
            "window_start": "2026-01-01",
            "window_end": "2026-01-31",
            "total_return_pct": 1.0,
        },
        {
            "group_id": 77,
            "run_id": 102,
            "window_index": 2,
            "window_start": "2026-02-01",
            "window_end": "2026-02-28",
            "total_return_pct": 2.0,
        },
        {
            "group_id": 77,
            "run_id": 103,
            "window_index": 3,
            "window_start": "2026-03-01",
            "window_end": "2026-03-31",
            "total_return_pct": 3.0,
        },
    ]


def test_walk_forward_service_rejects_empty_windows() -> None:
    with pytest.raises(ValueError, match="No walk-forward windows generated"):
        execute_walk_forward_backtest(
            conn=object(),
            cfg=_cfg(),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            windows=[],
            run_backtest_fn=lambda _conn, _cfg: _Result(run_id=1, total_return_pct=1.0),
            insert_group_fn=lambda _conn, **_kwargs: 1,
            insert_group_run_fn=lambda _conn, **_kwargs: None,
            commit_fn=lambda _conn: None,
        )
