from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import date
from typing import Any, Callable

from common.git import git_head_revision
from common.tickers import load_tickers_from_file
from common.time import utc_now_iso
from trading.backtesting.domain.optimization.objective import evaluate_candidate, select_winner
from trading.backtesting.domain.optimization.search import (
    canonical_params_json,
    generate_candidates,
    params_fingerprint,
)
from trading.backtesting.domain.windowing import build_walk_forward_optimization_splits
from trading.backtesting.models import (
    BACKTEST_PURPOSE_FINAL_HOLDOUT,
    BACKTEST_PURPOSE_STANDALONE,
    BACKTEST_PURPOSE_WALK_FORWARD_OOS,
    BacktestConfig,
    BacktestResult,
)
from trading.backtesting.optimizer_models import (
    MANIFEST_V1,
    CandidateResult,
    ExperimentStatus,
    FailureStage,
    HoldoutOutcome,
    OptimizationExperimentInsert,
    OptimizationManifestInsert,
    OptimizationSummary,
    OptimizationTrialInsert,
    OptimizationWindowInsert,
    OptimizerConfig,
    RunOutcome,
    WalkForwardSplit,
    WindowSelection,
)
from trading.backtesting.repositories.optimization_repository import (
    insert_experiment,
    insert_manifest,
    insert_trial,
    insert_window,
)
from trading.backtesting.services.backtest_data_service import build_monthly_universe, resolve_backtest_dates
from trading.domain.exceptions import NotFoundError, ValidationError
from trading.domain.strategies.resolution import resolve_strategy
from trading.models import AccountRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.book_bridge import strategy_id_for_label
from trading.repositories.books import BookRepository
from trading.repositories.strategies import StrategyRepository
from trading.repositories.unit_of_work import unit_of_work

# A metrics-only run computes performance without persisting; a persisted run writes a
# backtest_runs row (used for the winner's OOS and holdout evidence).
RunFn = Callable[[sqlite3.Connection, BacktestConfig], BacktestResult]

# Run-name prefix for persisted optimizer evidence, kept short for CLI readability.
OPTIMIZER_RUN_NAME_PREFIX = "wfo"


class OptimizationRunError(ValueError):
    """Internal signal that the window-search or holdout stage failed.

    Never crosses this module's boundary as itself: ``run_and_persist_optimization``
    catches it, persists a failed ``optimization_experiments`` row, and raises a
    plain ``ValidationError`` referencing that row, so callers keep matching
    ``except ValueError`` exactly as before. Carries the context needed to build
    that failure row: which stage failed, how many windows completed first, and
    the run's already-resolved date bounds.
    """

    def __init__(
        self,
        *,
        stage: FailureStage,
        windows_completed: int,
        start_date: date,
        end_date: date,
        cause: Exception,
    ) -> None:
        self.stage = stage
        self.windows_completed = windows_completed
        self.start_date = start_date
        self.end_date = end_date
        self.cause_message = str(cause)
        super().__init__(f"{stage} failed after {windows_completed} window(s): {cause}")


def run_walk_forward_optimization(
    conn: sqlite3.Connection,
    cfg: OptimizerConfig,
    *,
    run_metrics_only_fn: RunFn,
    run_persisted_fn: RunFn,
) -> OptimizationSummary:
    """Run one walk-forward optimization experiment over a single strategy.

    For each chronological window: evaluate every grid candidate on the training
    interval (persistence-free), freeze the best eligible candidate, then run that
    winner once over the out-of-sample interval. After all windows, run the
    forward-carried winner once over the untouched holdout. The strategy's default
    parameters are run over the same OOS/holdout intervals as a baseline. Training,
    OOS, and holdout evidence are kept strictly separate and never blended.

    The winner's OOS and holdout runs are persisted (purposes ``walk_forward_oos`` /
    ``final_holdout``); training trials and baseline comparison runs are metrics-only.
    """
    spec = resolve_strategy(cfg.strategy)
    default_params: dict[str, Any] = dict(spec.default_params)
    unknown = set(cfg.search_space) - set(default_params)
    if unknown:
        raise ValidationError(f"search_space keys are not parameters of strategy '{cfg.strategy}': {sorted(unknown)}")

    start_date, end_date = resolve_backtest_dates(cfg.start, cfg.end, cfg.lookback_months)
    splits, holdout = build_walk_forward_optimization_splits(
        start_date,
        end_date,
        train_months=cfg.train_months,
        test_months=cfg.test_months,
        step_months=cfg.step_months,
        holdout_months=cfg.holdout_months,
    )
    candidates = generate_candidates(cfg.search_space, budget=cfg.candidate_budget)

    window_selections: list[WindowSelection] = []
    try:
        for window_index, split in enumerate(splits, start=1):
            window_selections.append(
                _run_one_window(
                    conn,
                    cfg,
                    window_index=window_index,
                    split=split,
                    candidates=candidates,
                    run_metrics_only_fn=run_metrics_only_fn,
                    run_persisted_fn=run_persisted_fn,
                )
            )
    except Exception as error:
        raise OptimizationRunError(
            stage=FailureStage.WINDOW_SEARCH,
            windows_completed=len(window_selections),
            start_date=start_date,
            end_date=end_date,
            cause=error,
        ) from error

    try:
        holdout_outcome = _run_holdout(
            conn,
            cfg,
            holdout=holdout,
            window_selections=window_selections,
            run_metrics_only_fn=run_metrics_only_fn,
            run_persisted_fn=run_persisted_fn,
        )
    except Exception as error:
        raise OptimizationRunError(
            stage=FailureStage.HOLDOUT,
            windows_completed=len(window_selections),
            start_date=start_date,
            end_date=end_date,
            cause=error,
        ) from error

    return OptimizationSummary(
        strategy=cfg.strategy,
        account_name=cfg.account_name,
        objective_name=cfg.objective_name,
        default_params=default_params,
        windows=window_selections,
        holdout=holdout_outcome,
    )


def _run_one_window(
    conn: sqlite3.Connection,
    cfg: OptimizerConfig,
    *,
    window_index: int,
    split: WalkForwardSplit,
    candidates: list[dict[str, Any]],
    run_metrics_only_fn: RunFn,
    run_persisted_fn: RunFn,
) -> WindowSelection:
    """Select the window's winner on training data, then run it (and the default
    baseline) once over the out-of-sample interval."""
    winner, candidate_results = _select_window_winner(
        conn,
        cfg,
        split=split,
        candidates=candidates,
        run_metrics_only_fn=run_metrics_only_fn,
    )
    winner_oos = run_persisted_fn(
        conn,
        _config(
            cfg,
            start=split.test_start,
            end=split.test_end,
            param_override=winner.params,
            purpose=BACKTEST_PURPOSE_WALK_FORWARD_OOS,
            run_name=f"{OPTIMIZER_RUN_NAME_PREFIX}_w{window_index:02d}",
        ),
    )
    baseline_oos = run_metrics_only_fn(
        conn,
        _config(
            cfg,
            start=split.test_start,
            end=split.test_end,
            param_override=None,
            purpose=BACKTEST_PURPOSE_STANDALONE,
            run_name=None,
        ),
    )
    return WindowSelection(
        window_index=window_index,
        split=split,
        candidate_count=len(candidates),
        winner=winner,
        winner_oos=_run_outcome(winner_oos),
        baseline_oos=_run_outcome(baseline_oos),
        candidates=candidate_results,
    )


def run_and_persist_optimization(
    conn: sqlite3.Connection,
    cfg: OptimizerConfig,
    *,
    run_metrics_only_fn: RunFn,
    run_persisted_fn: RunFn,
    market_data_provider: str = "unknown",
) -> OptimizationSummary:
    """Run one optimization experiment and persist its Tier-1 record.

    Resolves the account and strategy *before* running anything — an unknown
    account/strategy fails immediately rather than after a full (possibly
    expensive) optimization run. Runs the pure orchestration, then writes one
    ``optimization_experiments`` row (config + forward-carried winner + OOS
    aggregate + holdout summary) plus the per-window/candidate audit and the
    frozen provenance manifest, and returns the summary with its ``experiment_id``
    set — the handle a later promotion uses.

    If the window-search or holdout stage raises, persists a failed experiment row
    (status/stage/message; see ``OptimizationRunError``) instead of losing the
    attempt, then raises ``ValidationError`` referencing that row's id.

    ``market_data_provider`` is the resolved provider name recorded on the manifest;
    the composition root binds it (it is infrastructure knowledge the service must
    not resolve itself).
    """
    now = utc_now_iso()
    account = AccountRepository(conn).fetch_by_name(cfg.account_name)
    if account is None:
        raise NotFoundError(f"Account not found: {cfg.account_name}")
    strategy_id = strategy_id_for_label(conn, cfg.strategy, now_iso=now)
    strategy_row = StrategyRepository(conn).fetch_by_id(strategy_id=strategy_id) if strategy_id is not None else None
    if strategy_row is None:
        raise NotFoundError(f"Strategy not found for optimizer target: {cfg.strategy}")

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
    payload = OptimizationExperimentInsert(
        account_id=account.id,
        strategy_id=strategy_id,
        primitive=primitive,
        objective_name=cfg.objective_name,
        search_space_json=json.dumps(cfg.search_space, sort_keys=True),
        candidate_budget=cfg.candidate_budget,
        train_months=cfg.train_months,
        test_months=cfg.test_months,
        step_months=cfg.step_months,
        holdout_months=cfg.holdout_months,
        warmup_months=cfg.warmup_months,
        start_date=error.start_date.isoformat(),
        end_date=error.end_date.isoformat(),
        window_count=error.windows_completed,
        winner_params_json=json.dumps(None),
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

    payload = OptimizationExperimentInsert(
        account_id=account.id,
        strategy_id=strategy_id,
        primitive=primitive,
        objective_name=cfg.objective_name,
        search_space_json=json.dumps(cfg.search_space, sort_keys=True),
        candidate_budget=cfg.candidate_budget,
        train_months=cfg.train_months,
        test_months=cfg.test_months,
        step_months=cfg.step_months,
        holdout_months=cfg.holdout_months,
        warmup_months=cfg.warmup_months,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        window_count=len(summary.windows),
        winner_params_json=json.dumps(winner_params, sort_keys=True),
        oos_mean_winner_return_pct=sum(winner_returns) / len(winner_returns),
        oos_mean_baseline_return_pct=sum(baseline_returns) / len(baseline_returns),
        oos_windows_beat_baseline=beat_baseline,
        holdout_run_id=summary.holdout.winner.run_id if summary.holdout is not None else None,
        holdout_winner_return_pct=summary.holdout.winner.total_return_pct if summary.holdout is not None else None,
        holdout_baseline_return_pct=(
            summary.holdout.baseline.total_return_pct if summary.holdout is not None else None
        ),
    )
    # Experiment row + its per-window/per-candidate audit tree + the frozen
    # provenance manifest land atomically.
    with unit_of_work(conn):
        experiment_id = insert_experiment(conn, payload, created_at=now)
        _persist_windows_and_trials(conn, experiment_id, summary)
        _persist_manifest(
            conn,
            experiment_id=experiment_id,
            cfg=cfg,
            account=account,
            start_date=start_date,
            end_date=end_date,
            market_data_provider=market_data_provider,
            now=now,
        )
    return experiment_id


def _persist_manifest(
    conn: sqlite3.Connection,
    *,
    experiment_id: int,
    cfg: OptimizerConfig,
    account: AccountRecord,
    start_date: date,
    end_date: date,
    market_data_provider: str,
    now: str,
) -> None:
    """Freeze one provenance manifest for the run (see ``OptimizationManifestInsert``).

    Snapshots the effective economics, the default book's risk/sizing knobs, the exact
    resolved universe membership + lineage, the configured provider, and the engine
    revision — the assumptions every candidate in this experiment shared.
    """
    book = BookRepository(conn).fetch_default_for_account(account_id=account.id)
    effective_execution = {
        "risk_policy": book.risk_policy if book is not None else None,
        "instrument_mode": book.instrument_mode if book is not None else None,
        "trade_size_pct": book.trade_size_pct if book is not None else None,
        "max_position_pct": book.max_position_pct if book is not None else None,
        "max_trades_per_run": book.max_trades_per_run if book is not None else None,
    }

    default_tickers = load_tickers_from_file(cfg.tickers_file)
    _month_to_tickers, all_tickers, _warnings = build_monthly_universe(
        default_tickers, start_date, end_date, cfg.universe_history_dir
    )
    universe = sorted(set(all_tickers))

    insert_manifest(
        conn,
        OptimizationManifestInsert(
            experiment_id=experiment_id,
            manifest_version=MANIFEST_V1,
            account_name=account.name,
            book_id=book.id if book is not None else None,
            initial_cash=account.initial_cash,
            benchmark_ticker=account.benchmark_ticker,
            slippage_bps=cfg.slippage_bps,
            fee_per_trade=cfg.fee_per_trade,
            effective_execution_json=json.dumps(effective_execution, sort_keys=True),
            tickers_file=cfg.tickers_file,
            universe_history_dir=cfg.universe_history_dir,
            universe_tickers_json=json.dumps(universe),
            universe_size=len(universe),
            market_data_provider=market_data_provider,
            data_as_of=now,
            engine_revision=git_head_revision(),
        ),
        created_at=now,
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
                    params_json=canonical_params_json(candidate.params),
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


def _select_window_winner(
    conn: sqlite3.Connection,
    cfg: OptimizerConfig,
    *,
    split: WalkForwardSplit,
    candidates: list[dict[str, Any]],
    run_metrics_only_fn: RunFn,
) -> tuple[CandidateResult, list[CandidateResult]]:
    """Return the window's winner and every evaluated candidate.

    The full candidate list is carried out (not just the winner) so the attempted
    search can be persisted as the per-window multiple-testing audit record.
    """
    results: list[CandidateResult] = []
    for index, params in enumerate(candidates):
        train_result = run_metrics_only_fn(
            conn,
            _config(
                cfg,
                start=split.train_start,
                end=split.train_end,
                param_override=params,
                purpose=BACKTEST_PURPOSE_STANDALONE,
                run_name=None,
            ),
        )
        results.append(
            evaluate_candidate(
                index=index,
                params=params,
                annualized_return_pct=train_result.annualized_return_pct,
                max_drawdown_pct=train_result.max_drawdown_pct,
                trade_count=train_result.trade_count,
            )
        )
    try:
        return select_winner(results), results
    except ValidationError as error:
        raise ValidationError(
            f"Training window {split.train_start.isoformat()}..{split.train_end.isoformat()}: {error}"
        ) from error


def _run_holdout(
    conn: sqlite3.Connection,
    cfg: OptimizerConfig,
    *,
    holdout: tuple[date, date] | None,
    window_selections: list[WindowSelection],
    run_metrics_only_fn: RunFn,
    run_persisted_fn: RunFn,
) -> HoldoutOutcome | None:
    if holdout is None or not window_selections:
        return None

    # Forward-carry the most recent window's winner — the parameters the process would
    # take into the future — and evaluate them once on the untouched holdout.
    winner_params = window_selections[-1].winner.params
    holdout_start, holdout_end = holdout
    winner_result = run_persisted_fn(
        conn,
        _config(
            cfg,
            start=holdout_start,
            end=holdout_end,
            param_override=winner_params,
            purpose=BACKTEST_PURPOSE_FINAL_HOLDOUT,
            run_name=f"{OPTIMIZER_RUN_NAME_PREFIX}_holdout",
        ),
    )
    baseline_result = run_metrics_only_fn(
        conn,
        _config(
            cfg,
            start=holdout_start,
            end=holdout_end,
            param_override=None,
            purpose=BACKTEST_PURPOSE_STANDALONE,
            run_name=None,
        ),
    )
    return HoldoutOutcome(
        holdout_start=holdout_start,
        holdout_end=holdout_end,
        winner_params=winner_params,
        winner=_run_outcome(winner_result),
        baseline=_run_outcome(baseline_result),
    )


def _config(
    cfg: OptimizerConfig,
    *,
    start: date,
    end: date,
    param_override: dict[str, Any] | None,
    purpose: str,
    run_name: str | None,
) -> BacktestConfig:
    return BacktestConfig(
        account_name=cfg.account_name,
        tickers_file=cfg.tickers_file,
        universe_history_dir=cfg.universe_history_dir,
        start=start.isoformat(),
        end=end.isoformat(),
        lookback_months=None,
        slippage_bps=cfg.slippage_bps,
        fee_per_trade=cfg.fee_per_trade,
        run_name=run_name,
        allow_approximate_leaps=cfg.allow_approximate_leaps,
        strategy=cfg.strategy,
        purpose=purpose,
        param_override=param_override,
        warmup_months=cfg.warmup_months,
    )


def _run_outcome(result: BacktestResult) -> RunOutcome:
    return RunOutcome(
        run_id=result.run_id,
        total_return_pct=result.total_return_pct,
        annualized_return_pct=result.annualized_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        calmar_ratio=result.calmar_ratio,
        trade_count=result.trade_count,
        benchmark_return_pct=result.benchmark_return_pct,
    )
