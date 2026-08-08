"""Research evidence for a strategy, summarized from this package's records.

The read surface the trading side uses. Promotion and evaluation need to know what
a strategy's research says, not how backtest runs, holdout runs, optimizer
experiments, and OOS windows relate to one another — so the joining and the
not-found handling live here, beside the tables, and the caller receives a finished
``Evaluation*Evidence`` record.

Those records are `trading.models.evaluation` contracts rather than types of this
package's own: `models/` is the lowest layer, and the evidence is *for* evaluation.
"""

from __future__ import annotations

import sqlite3
from statistics import median

from backtesting.domain.metrics import max_drawdown_pct
from backtesting.repositories.optimization import (
    fetch_latest_experiment_for_account_strategy,
)
from backtesting.repositories.runs import (
    fetch_backtest_report_run,
    fetch_backtest_report_snapshots,
    fetch_backtest_report_trades,
)
from backtesting.services.optimizer_aggregation_service import fetch_oos_segments
from common.coercion import row_float, row_str
from trading.domain.returns import safe_return_pct
from trading.models.evaluation import EvaluationBacktestEvidence, EvaluationWalkForwardEvidence


def build_backtest_evidence(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    requested_strategy: str,
) -> EvaluationBacktestEvidence:
    """Build backtest evidence from the strategy's latest experiment holdout run.

    The holdout is the one run whose parameters *and* date range were committed
    before it executed (the forward-carried winner, evaluated once on data the
    search never touched), which is why it — rather than a standalone backtest
    over an operator-chosen range — is what promotion reads.

    Caveat when the experiment *targeted* this strategy rather than producing it:
    the holdout ran the tuned winner's parameters, not the strategy's defaults, so
    the numbers are an upper bound for that strategy family. Evidence attributed
    via ``promoted_strategy_id`` has no such gap — there the winner's parameters
    are exactly the variant's.
    """
    experiment = fetch_latest_experiment_for_account_strategy(
        conn,
        account_id=account_id,
        strategy_name=requested_strategy,
    )
    if experiment is None or experiment.holdout_run_id is None:
        return EvaluationBacktestEvidence()
    run_id = experiment.holdout_run_id

    run = fetch_backtest_report_run(conn, run_id)
    snapshots = fetch_backtest_report_snapshots(conn, run_id)
    trades = fetch_backtest_report_trades(conn, run_id)
    if run is None or not snapshots:
        return EvaluationBacktestEvidence(
            run_id=run_id,
            available=False,
        )

    starting_equity = row_float(snapshots[0], "equity")
    ending_equity = row_float(snapshots[-1], "equity")
    equity_curve = [value for value in (row_float(item, "equity") for item in snapshots) if value is not None]
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
        max_drawdown_pct=max_drawdown_pct(equity_curve),
        warnings=row_str(run, "warnings"),
    )


def build_walk_forward_evidence(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    requested_strategy: str,
) -> EvaluationWalkForwardEvidence:
    """Build walk-forward evidence from the strategy's latest experiment windows.

    Each window's return is derived from its persisted OOS run's equity marks
    rather than a stored aggregate, so the distribution cannot drift from the runs
    it summarizes. The windows measure the *process* — retune on each training
    interval, then run out-of-sample — which is what walk-forward evidence is for.
    """
    experiment = fetch_latest_experiment_for_account_strategy(
        conn,
        account_id=account_id,
        strategy_name=requested_strategy,
    )
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
