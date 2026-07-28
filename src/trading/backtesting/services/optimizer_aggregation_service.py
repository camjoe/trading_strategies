"""Read-side aggregation over a persisted walk-forward optimization experiment.

Assembles the compounded out-of-sample series from the experiment's persisted
windows (revision ``0022``): read each window's linked OOS run equity marks,
derive its return, and compound the non-overlapping windows into one chronological
series. Nothing is stored — the series is derived on read from the window rows and
their ``backtest_runs`` OOS runs (link-don't-copy), so it stays consistent with the
member runs.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from trading.backtesting.domain.optimization.aggregation import compound_oos_returns, period_return_pct
from trading.backtesting.optimizer_models import CompoundedOOSSeries, OOSReturnSegment
from trading.backtesting.repositories.optimization_repository import fetch_windows_for_experiment
from trading.backtesting.repositories.report_repository import fetch_backtest_run_equity_bounds


def fetch_oos_segments(conn: sqlite3.Connection, *, experiment_id: int) -> list[OOSReturnSegment] | None:
    """Return one OOS segment per persisted window, or ``None`` if unavailable.

    ``None`` when the experiment has no persisted windows (predates revision ``0022``)
    or any window's OOS run has no equity snapshots — the record is only honest if
    every window contributes, so a missing segment yields nothing rather than a
    partial series.
    """
    windows = fetch_windows_for_experiment(conn, experiment_id=experiment_id)
    if not windows:
        return None

    segments: list[OOSReturnSegment] = []
    for window in windows:
        bounds = fetch_backtest_run_equity_bounds(conn, run_id=window.oos_run_id)
        if bounds is None:
            return None
        first_equity, last_equity = bounds
        segments.append(
            OOSReturnSegment(
                window_index=window.window_index,
                test_start=date.fromisoformat(window.test_start),
                test_end=date.fromisoformat(window.test_end),
                return_pct=period_return_pct(first_equity=first_equity, last_equity=last_equity),
            )
        )
    return segments


def fetch_compounded_oos(conn: sqlite3.Connection, *, experiment_id: int) -> CompoundedOOSSeries | None:
    """Return the experiment's compounded OOS series, or ``None`` if unavailable."""
    segments = fetch_oos_segments(conn, experiment_id=experiment_id)
    return None if segments is None else compound_oos_returns(segments)
