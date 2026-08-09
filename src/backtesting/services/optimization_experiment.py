"""Persisting one walk-forward experiment: the record, its audit tree, its manifest.

Runs the search in :mod:`backtesting.services.walk_forward_optimizer` and
writes what it found to the four ``optimization_*`` tables. A failed sweep still
gets a row, so the attempt is diagnosable rather than lost.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import date
from functools import partial
from typing import Callable

from backtesting.domain.optimization.search import params_fingerprint
from backtesting.models.optimizer import (
    MANIFEST_V1,
    ExperimentStatus,
    OptimizationExperimentInsert,
    OptimizationManifestInsert,
    OptimizationSummary,
    OptimizationTrialInsert,
    OptimizationWindowInsert,
    OptimizerConfig,
)
from backtesting.repositories.optimization import (
    insert_experiment,
    insert_manifest,
    insert_trial,
    insert_window,
)
from backtesting.services.run_inputs import resolve_universe
from backtesting.services.walk_forward_optimizer import (
    OptimizationRunError,
    RunFn,
    run_walk_forward_optimization,
)
from common.git import git_head_revision
from common.time import utc_now_iso
from trading.domain.exceptions import NotFoundError, ValidationError
from trading.models import AccountRecord
from trading.models.books import BookRecord
from trading.persistence.json_columns import dumps_json_column
from trading.persistence.unit_of_work import unit_of_work
from trading.services.accounts import find_account
from trading.services.books.book_assignments import get_default_book
from trading.services.strategy_catalog.resolution import resolve_or_draft_strategy_record


def run_and_persist_optimization(
    conn: sqlite3.Connection,
    cfg: OptimizerConfig,
    *,
    run_metrics_only_fn: RunFn,
    run_persisted_fn: RunFn,
    market_data_provider: str = "unknown",
) -> OptimizationSummary:
    """Run one optimization experiment and persist its record.

    The account and strategy resolve *before* anything runs, so an unknown one
    fails in a second rather than after a full sweep. The returned summary carries
    the ``experiment_id`` a later promotion uses.

    A window-search or holdout failure still persists an experiment row, so a
    failed attempt is diagnosable rather than lost; the raised ``ValidationError``
    names it.

    ``market_data_provider`` is bound by the composition root — which provider is
    configured is infrastructure knowledge this service must not resolve itself.
    """
    now = utc_now_iso()
    account = find_account(conn, cfg.account_name)
    if account is None:
        raise NotFoundError(f"Account not found: {cfg.account_name}")
    strategy_row = resolve_or_draft_strategy_record(conn, cfg.strategy, now_iso=now)
    if strategy_row is None:
        raise NotFoundError(f"Strategy not found for optimizer target: {cfg.strategy}")
    strategy_id = strategy_row.id

    try:
        summary = run_walk_forward_optimization(
            conn,
            cfg,
            run_metrics_only_fn=run_metrics_only_fn,
            run_persisted_fn=run_persisted_fn,
        )
    except OptimizationRunError as error:
        experiment_id = _persist_failed_experiment(
            conn,
            cfg,
            account=account,
            strategy_id=strategy_id,
            primitive=strategy_row.primitive,
            error=error,
            now=now,
        )
        raise ValidationError(
            f"{error} Persisted failed experiment #{experiment_id} — "
            f"see 'backtest-optimize-show {experiment_id}' for diagnostics."
        ) from error

    experiment_id = _persist_experiment(
        conn,
        cfg,
        summary,
        account=account,
        strategy_id=strategy_id,
        primitive=strategy_row.primitive,
        market_data_provider=market_data_provider,
        now=now,
    )
    return replace(summary, experiment_id=experiment_id)


def _experiment_insert_for(
    cfg: OptimizerConfig,
    *,
    account: AccountRecord,
    strategy_id: int | None,
    primitive: str,
) -> Callable[..., OptimizationExperimentInsert]:
    """The config half of an experiment row, bound; callers add the outcome half.

    Completed and failed rows record the same search configuration and differ only
    in what they found. Building it once means a new config field cannot reach one
    row and miss the other — and the failed path is the one nobody exercises.
    """
    return partial(
        OptimizationExperimentInsert,
        account_id=account.id,
        strategy_id=strategy_id,
        primitive=primitive,
        objective_name=cfg.objective_name,
        search_space_json=dumps_json_column(cfg.search_space),
        candidate_budget=cfg.candidate_budget,
        train_months=cfg.train_months,
        test_months=cfg.test_months,
        step_months=cfg.step_months,
        holdout_months=cfg.holdout_months,
        warmup_months=cfg.warmup_months,
    )


def _persist_failed_experiment(
    conn: sqlite3.Connection,
    cfg: OptimizerConfig,
    *,
    account: AccountRecord,
    strategy_id: int | None,
    primitive: str,
    error: OptimizationRunError,
    now: str,
) -> int:
    """Persist a minimal audit row for a run that failed mid-flight.

    No ``optimization_windows``/``optimization_trials``/manifest rows are written —
    a failed experiment gets exactly this one record, not a partial audit tree.
    """
    payload = _experiment_insert_for(cfg, account=account, strategy_id=strategy_id, primitive=primitive)(
        start_date=error.start_date.isoformat(),
        end_date=error.end_date.isoformat(),
        window_count=error.windows_completed,
        winner_params_json=dumps_json_column(None),
        oos_mean_winner_return_pct=None,
        oos_mean_baseline_return_pct=None,
        oos_windows_beat_baseline=None,
        holdout_run_id=None,
        holdout_winner_return_pct=None,
        holdout_baseline_return_pct=None,
        status=ExperimentStatus.FAILED,
        failure_stage=error.stage,
        failure_message=error.cause_message,
    )
    return insert_experiment(conn, payload, created_at=now)


def _persist_experiment(
    conn: sqlite3.Connection,
    cfg: OptimizerConfig,
    summary: OptimizationSummary,
    *,
    account: AccountRecord,
    strategy_id: int | None,
    primitive: str,
    market_data_provider: str,
    now: str,
) -> int:
    if not summary.windows:
        raise ValidationError("Optimization produced no windows; nothing to persist or promote.")

    winner_params = summary.windows[-1].winner.params
    winner_returns = [w.winner_oos.total_return_pct for w in summary.windows]
    baseline_returns = [w.baseline_oos.total_return_pct for w in summary.windows]
    beat_baseline = sum(1 for w in summary.windows if w.winner_oos.total_return_pct > w.baseline_oos.total_return_pct)
    start_date = summary.windows[0].split.train_start
    end_date = summary.holdout.holdout_end if summary.holdout is not None else summary.windows[-1].split.test_end

    payload = _experiment_insert_for(cfg, account=account, strategy_id=strategy_id, primitive=primitive)(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        window_count=len(summary.windows),
        winner_params_json=dumps_json_column(winner_params),
        oos_mean_winner_return_pct=sum(winner_returns) / len(winner_returns),
        oos_mean_baseline_return_pct=sum(baseline_returns) / len(baseline_returns),
        oos_windows_beat_baseline=beat_baseline,
        holdout_run_id=summary.holdout.winner.run_id if summary.holdout is not None else None,
        holdout_winner_return_pct=summary.holdout.winner.total_return_pct if summary.holdout is not None else None,
        holdout_baseline_return_pct=(
            summary.holdout.baseline.total_return_pct if summary.holdout is not None else None
        ),
    )

    # Gathered before the transaction opens: the manifest reads ticker files off
    # disk and shells out for the engine revision, and neither belongs inside an
    # open write transaction.
    manifest_inputs = _resolve_manifest_inputs(conn, cfg, account=account, start_date=start_date, end_date=end_date)

    # Experiment row + its per-window/per-candidate audit tree + the frozen
    # provenance manifest land atomically.
    with unit_of_work(conn):
        experiment_id = insert_experiment(conn, payload, created_at=now)
        _persist_windows_and_trials(conn, experiment_id, summary)
        insert_manifest(
            conn,
            _manifest_insert(
                manifest_inputs,
                experiment_id=experiment_id,
                cfg=cfg,
                account=account,
                market_data_provider=market_data_provider,
                now=now,
            ),
            created_at=now,
        )
    return experiment_id


@dataclass(frozen=True)
class _ManifestInputs:
    """The manifest's facts that come from outside the database."""

    book: BookRecord | None
    universe: list[str]
    engine_revision: str | None


def _resolve_manifest_inputs(
    conn: sqlite3.Connection,
    cfg: OptimizerConfig,
    *,
    account: AccountRecord,
    start_date: date,
    end_date: date,
) -> _ManifestInputs:
    return _ManifestInputs(
        book=get_default_book(conn, account_id=account.id),
        # Sorted and de-duplicated: a provenance record has to compare equal
        # across runs that resolved the same membership.
        universe=sorted(
            set(
                resolve_universe(
                    tickers_file=cfg.tickers_file,
                    universe_history_dir=cfg.universe_history_dir,
                    start_date=start_date,
                    end_date=end_date,
                ).all_tickers
            )
        ),
        engine_revision=git_head_revision(),
    )


def _manifest_insert(
    inputs: _ManifestInputs,
    *,
    experiment_id: int,
    cfg: OptimizerConfig,
    account: AccountRecord,
    market_data_provider: str,
    now: str,
) -> OptimizationManifestInsert:
    """One frozen provenance manifest: the assumptions every candidate shared.

    Effective economics, the default book's risk/sizing knobs, the resolved
    universe and its lineage, the provider, and the engine revision.
    """
    book = inputs.book
    effective_execution = {
        "risk_policy": book.risk_policy if book is not None else None,
        "instrument_mode": book.instrument_mode if book is not None else None,
        "trade_size_pct": book.trade_size_pct if book is not None else None,
        "max_position_pct": book.max_position_pct if book is not None else None,
        "max_trades_per_run": book.max_trades_per_run if book is not None else None,
    }
    return OptimizationManifestInsert(
        experiment_id=experiment_id,
        manifest_version=MANIFEST_V1,
        account_name=account.name,
        book_id=book.id if book is not None else None,
        initial_cash=account.initial_cash,
        benchmark_ticker=account.benchmark_ticker,
        slippage_bps=cfg.slippage_bps,
        fee_per_trade=cfg.fee_per_trade,
        effective_execution_json=dumps_json_column(effective_execution),
        tickers_file=cfg.tickers_file,
        universe_history_dir=cfg.universe_history_dir,
        universe_tickers_json=dumps_json_column(inputs.universe),
        universe_size=len(inputs.universe),
        market_data_provider=market_data_provider,
        data_as_of=now,
        engine_revision=inputs.engine_revision,
    )


def _persist_windows_and_trials(conn: sqlite3.Connection, experiment_id: int, summary: OptimizationSummary) -> None:
    """Persist one ``optimization_windows`` row per window and one
    ``optimization_trials`` row per evaluated candidate.

    The window links its winner's persisted OOS run (``oos_run_id``); each trial
    records a candidate's objective evidence, and the window winner is flagged
    ``selected``. Runs inside the experiment's ``unit_of_work``.
    """
    for window in summary.windows:
        window_id = insert_window(
            conn,
            OptimizationWindowInsert(
                experiment_id=experiment_id,
                window_index=window.window_index,
                train_start=window.split.train_start.isoformat(),
                train_end=window.split.train_end.isoformat(),
                test_start=window.split.test_start.isoformat(),
                test_end=window.split.test_end.isoformat(),
                oos_run_id=window.winner_oos.run_id,
            ),
        )
        for candidate in window.candidates:
            insert_trial(
                conn,
                OptimizationTrialInsert(
                    window_id=window_id,
                    candidate_index=candidate.index,
                    params_json=dumps_json_column(candidate.params),
                    params_hash=params_fingerprint(candidate.params),
                    objective_value=candidate.score,
                    annualized_return_pct=candidate.annualized_return_pct,
                    max_drawdown_pct=candidate.max_drawdown_pct,
                    trade_count=candidate.trade_count,
                    eligible=candidate.eligible,
                    rejection_reason=candidate.rejection_reason,
                    selected=candidate.index == window.winner.index,
                ),
            )
