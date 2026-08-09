"""Read-side aggregation over a persisted walk-forward optimization experiment.

Nothing here is stored. Both shapes are derived on each read from the window rows
(revision ``0022``) and the ``backtest_runs`` OOS runs they link to, so neither
can drift from the runs it summarizes.

Not a seam itself: it serves the two that are, ``evidence`` wanting the
per-window segments and ``audit`` the compounded series.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from backtesting.domain.metrics import total_return_pct
from backtesting.domain.optimization import compound_oos_returns
from backtesting.models.optimizer import CompoundedOOSSeries, OOSReturnSegment
from backtesting.repositories.optimization import fetch_windows_for_experiment
from backtesting.repositories.runs import fetch_run_equity_bounds


def fetch_oos_segments(conn: sqlite3.Connection, *, experiment_id: int) -> list[OOSReturnSegment] | None:
    """One OOS segment per persisted window, or ``None``.

    All or nothing: ``None`` when the experiment has no persisted windows, or when
    any window's OOS run has no equity snapshots. A partial series would read as a
    complete record of a shorter experiment.
    """
    windows = fetch_windows_for_experiment(conn, experiment_id=experiment_id)
    if not windows:
        return None

    segments: list[OOSReturnSegment] = []
    for window in windows:
        bounds = fetch_run_equity_bounds(conn, run_id=window.oos_run_id)
        if bounds is None:
            return None
        first_equity, last_equity = bounds
        segments.append(
            OOSReturnSegment(
                window_index=window.window_index,
                test_start=date.fromisoformat(window.test_start),
                test_end=date.fromisoformat(window.test_end),
                return_pct=total_return_pct(first_equity=first_equity, last_equity=last_equity),
            )
        )
    return segments


def fetch_compounded_oos(conn: sqlite3.Connection, *, experiment_id: int) -> CompoundedOOSSeries | None:
    """Return the experiment's compounded OOS series, or ``None`` if unavailable."""
    segments = fetch_oos_segments(conn, experiment_id=experiment_id)
    return None if segments is None else compound_oos_returns(segments)
