"""The walk-forward search itself: windows, candidates, winners, holdout.

Persists nothing and touches no repository. What it returns is an
``OptimizationSummary`` — a record of what the search found, which
:mod:`backtesting.services.optimization_experiment` turns into rows.
Keeping the two apart is what lets a benchmark harness run a full sweep without
writing an experiment.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, Callable

from backtesting.domain.optimization.objective import evaluate_candidate, select_winner
from backtesting.domain.optimization.search import generate_candidates
from backtesting.domain.windowing import build_walk_forward_optimization_splits, resolve_run_window
from backtesting.models import (
    BACKTEST_PURPOSE_FINAL_HOLDOUT,
    BACKTEST_PURPOSE_STANDALONE,
    BACKTEST_PURPOSE_WALK_FORWARD_OOS,
    BacktestConfig,
    BacktestResult,
)
from backtesting.models.optimizer import (
    CandidateResult,
    FailureStage,
    HoldoutOutcome,
    OptimizationSummary,
    OptimizerConfig,
    RunOutcome,
    WalkForwardSplit,
    WindowSelection,
)
from trading.domain.exceptions import ValidationError
from trading.domain.strategies.resolution import resolve_strategy

# A metrics-only run computes performance without persisting; a persisted run writes a
# backtest_runs row (used for the winner's OOS and holdout evidence).
RunFn = Callable[[sqlite3.Connection, BacktestConfig], BacktestResult]

# Run-name prefix for persisted optimizer evidence, kept short for CLI readability.
OPTIMIZER_RUN_NAME_PREFIX = "wfo"


class OptimizationRunError(ValueError):
    """Internal signal that the window-search or holdout stage failed.

    Never leaves this module as itself: ``run_and_persist_optimization`` catches
    it, records a failed experiment row, and re-raises a plain ``ValidationError``.
    Its fields are what that row needs.
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

    start_date, end_date = resolve_run_window(cfg.start, cfg.end, cfg.lookback_months)
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
