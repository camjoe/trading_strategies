from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import date
from typing import Any, Callable

from common.time import utc_now_iso
from trading.backtesting.domain.optimization.objective import evaluate_candidate, select_winner
from trading.backtesting.domain.optimization.search import generate_candidates
from trading.backtesting.domain.windowing import build_walk_forward_optimization_splits
from trading.backtesting.models import (
    BACKTEST_PURPOSE_FINAL_HOLDOUT,
    BACKTEST_PURPOSE_STANDALONE,
    BACKTEST_PURPOSE_WALK_FORWARD_OOS,
    BacktestConfig,
    BacktestResult,
)
from trading.backtesting.optimizer_models import (
    CandidateResult,
    HoldoutOutcome,
    OptimizationExperimentInsert,
    OptimizationSummary,
    OptimizerConfig,
    RunOutcome,
    WalkForwardSplit,
    WindowSelection,
)
from trading.backtesting.repositories.optimization_repository import insert_experiment
from trading.backtesting.services.backtest_data_service import resolve_backtest_dates
from trading.domain.exceptions import NotFoundError, ValidationError
from trading.domain.strategies.resolution import resolve_strategy
from trading.repositories.accounts import AccountRepository
from trading.repositories.book_bridge import strategy_id_for_label
from trading.repositories.strategies import StrategyRepository

# A metrics-only run computes performance without persisting; a persisted run writes a
# backtest_runs row (used for the winner's OOS and holdout evidence).
RunFn = Callable[[sqlite3.Connection, BacktestConfig], BacktestResult]

# Run-name prefix for persisted optimizer evidence, kept short for CLI readability.
OPTIMIZER_RUN_NAME_PREFIX = "wfo"


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
    for window_index, split in enumerate(splits, start=1):
        winner = _select_window_winner(
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
        window_selections.append(
            WindowSelection(
                window_index=window_index,
                split=split,
                candidate_count=len(candidates),
                winner=winner,
                winner_oos=_run_outcome(winner_oos),
                baseline_oos=_run_outcome(baseline_oos),
            )
        )

    holdout_outcome = _run_holdout(
        conn,
        cfg,
        holdout=holdout,
        window_selections=window_selections,
        run_metrics_only_fn=run_metrics_only_fn,
        run_persisted_fn=run_persisted_fn,
    )

    return OptimizationSummary(
        strategy=cfg.strategy,
        account_name=cfg.account_name,
        objective_name=cfg.objective_name,
        default_params=default_params,
        windows=window_selections,
        holdout=holdout_outcome,
    )


def run_and_persist_optimization(
    conn: sqlite3.Connection,
    cfg: OptimizerConfig,
    *,
    run_metrics_only_fn: RunFn,
    run_persisted_fn: RunFn,
) -> OptimizationSummary:
    """Run one optimization experiment and persist its Tier-1 record.

    Runs the pure orchestration, then writes one ``optimization_experiments`` row
    (config + forward-carried winner + OOS aggregate + holdout summary) and returns
    the summary with its ``experiment_id`` set — the handle a later promotion uses.
    """
    summary = run_walk_forward_optimization(
        conn,
        cfg,
        run_metrics_only_fn=run_metrics_only_fn,
        run_persisted_fn=run_persisted_fn,
    )
    experiment_id = _persist_experiment(conn, cfg, summary)
    return replace(summary, experiment_id=experiment_id)


def _persist_experiment(conn: sqlite3.Connection, cfg: OptimizerConfig, summary: OptimizationSummary) -> int:
    if not summary.windows:
        raise ValidationError("Optimization produced no windows; nothing to persist or promote.")

    now = utc_now_iso()
    account = AccountRepository(conn).fetch_by_name(cfg.account_name)
    if account is None:
        raise NotFoundError(f"Account not found: {cfg.account_name}")
    strategy_id = strategy_id_for_label(conn, cfg.strategy, now_iso=now)
    strategy_row = StrategyRepository(conn).fetch_by_id(strategy_id=strategy_id) if strategy_id is not None else None
    if strategy_row is None:
        raise NotFoundError(f"Strategy not found for optimizer target: {cfg.strategy}")

    winner_params = summary.windows[-1].winner.params
    winner_returns = [w.winner_oos.total_return_pct for w in summary.windows]
    baseline_returns = [w.baseline_oos.total_return_pct for w in summary.windows]
    beat_baseline = sum(1 for w in summary.windows if w.winner_oos.total_return_pct > w.baseline_oos.total_return_pct)
    start_date = summary.windows[0].split.train_start
    end_date = summary.holdout.holdout_end if summary.holdout is not None else summary.windows[-1].split.test_end

    payload = OptimizationExperimentInsert(
        account_id=account.id,
        strategy_id=strategy_id,
        primitive=strategy_row.primitive,
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
    return insert_experiment(conn, payload, created_at=now)


def _select_window_winner(
    conn: sqlite3.Connection,
    cfg: OptimizerConfig,
    *,
    split: WalkForwardSplit,
    candidates: list[dict[str, Any]],
    run_metrics_only_fn: RunFn,
) -> CandidateResult:
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
        return select_winner(results)
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
