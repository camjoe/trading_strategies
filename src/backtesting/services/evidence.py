"""A strategy's research evidence, joined from this package's records.

One of the two seams the trading side reads (the other is
:mod:`backtesting.services.audit`).

Returns ``trading.models.evaluation`` contracts rather than this package's own
types: ``models/`` is the lowest layer, shared by both contexts, and the evidence
is *for* evaluation.
"""

from __future__ import annotations

import sqlite3
from statistics import median

from backtesting.domain.metrics import equity_curve_from_rows, max_drawdown_pct
from backtesting.models.optimizer import OptimizationExperimentRecord
from backtesting.repositories.optimization import (
    fetch_latest_experiment_for_account_strategy,
)
from backtesting.repositories.runs import (
    fetch_run,
    fetch_snapshots,
    fetch_trades,
)
from backtesting.services.optimizer_aggregation import fetch_oos_segments
from common.coercion import row_float, row_str
from trading.domain.returns import safe_return_pct
from trading.models.evaluation import EvaluationBacktestEvidence, EvaluationWalkForwardEvidence


def build_strategy_evidence(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    requested_strategy: str,
) -> tuple[EvaluationBacktestEvidence, EvaluationWalkForwardEvidence]:
    """Both evidence records for a strategy, off one lookup of its latest experiment.

    Built as a pair because both read the same experiment row.
    """
    experiment = fetch_latest_experiment_for_account_strategy(
        conn,
        account_id=account_id,
        strategy_name=requested_strategy,
    )
    return _backtest_evidence(conn, experiment), _walk_forward_evidence(conn, experiment)


def _backtest_evidence(
    conn: sqlite3.Connection,
    experiment: OptimizationExperimentRecord | None,
) -> EvaluationBacktestEvidence:
    """Backtest evidence from the experiment's holdout run.

    The holdout, not a standalone backtest: its parameters and its date range were
    both committed before it executed.

    An upper bound rather than a like-for-like reading when the experiment
    *targeted* this strategy instead of producing it — the holdout ran the tuned
    winner's parameters, not the strategy's defaults. Evidence attributed via
    ``promoted_strategy_id`` has no such gap.
    """
    if experiment is None or experiment.holdout_run_id is None:
        return EvaluationBacktestEvidence()
    run_id = experiment.holdout_run_id

    run = fetch_run(conn, run_id)
    snapshots = fetch_snapshots(conn, run_id)
    trades = fetch_trades(conn, run_id)
    if run is None or not snapshots:
        return EvaluationBacktestEvidence(run_id=run_id, available=False)

    starting_equity = row_float(snapshots[0], "equity")
    ending_equity = row_float(snapshots[-1], "equity")
    return EvaluationBacktestEvidence(
        available=True,
        run_id=run_id,
        run_name=row_str(run, "run_name"),
        start_date=row_str(run, "start_date"),
        end_date=row_str(run, "end_date"),
        created_at=row_str(run, "created_at"),
        trade_count=len(trades),
        snapshot_count=len(snapshots),
        starting_equity=starting_equity,
        ending_equity=ending_equity,
        total_return_pct=safe_return_pct(starting_equity, ending_equity),
        max_drawdown_pct=max_drawdown_pct(equity_curve_from_rows(snapshots)),
        warnings=row_str(run, "warnings"),
    )


def _walk_forward_evidence(
    conn: sqlite3.Connection,
    experiment: OptimizationExperimentRecord | None,
) -> EvaluationWalkForwardEvidence:
    """Walk-forward evidence from the experiment's windows.

    Window returns come from each OOS run's equity marks, not a stored aggregate,
    so the distribution cannot drift from the runs it summarizes.
    """
    if experiment is None:
        return EvaluationWalkForwardEvidence()

    segments = fetch_oos_segments(conn, experiment_id=experiment.id)
    if not segments:
        return EvaluationWalkForwardEvidence()

    window_returns = [segment.return_pct for segment in segments]
    return EvaluationWalkForwardEvidence(
        available=True,
        window_returns=window_returns,
        average_return_pct=sum(window_returns) / len(window_returns),
        median_return_pct=float(median(window_returns)),
        best_return_pct=max(window_returns),
        worst_return_pct=min(window_returns),
    )
