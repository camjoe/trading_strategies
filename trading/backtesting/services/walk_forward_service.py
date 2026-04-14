from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from uuid import uuid4

from trading.backtesting.models import BacktestConfig, WalkForwardSummary
from trading.backtesting.repositories.walk_forward_repository import (
    insert_walk_forward_group,
    insert_walk_forward_group_run,
)

# Walk-forward backtest runs keep the existing short "wf" prefix for CLI readability.
WALK_FORWARD_RUN_NAME_PREFIX = "wf"

# Window numbers are zero-padded to keep run names stable in lexical ordering.
WINDOW_NUMBER_WIDTH = 2


@dataclass(frozen=True)
class _WalkForwardWindowResult:
    run_id: int
    window_index: int
    window_start: str
    window_end: str
    total_return_pct: float


def _normalized_run_name_prefix(run_name_prefix: str | None) -> str | None:
    if run_name_prefix is None:
        return None
    normalized = run_name_prefix.strip()
    return normalized or None


def _build_window_run_name(*, run_name_prefix: str | None, window_index: int) -> str:
    suffix = f"{window_index:0{WINDOW_NUMBER_WIDTH}d}"
    if run_name_prefix is None:
        return f"{WALK_FORWARD_RUN_NAME_PREFIX}_{suffix}"
    return f"{WALK_FORWARD_RUN_NAME_PREFIX}_{run_name_prefix}_{suffix}"


def _build_walk_forward_summary(
    *,
    account_name: str,
    start_date,
    end_date,
    window_results: list[_WalkForwardWindowResult],
) -> WalkForwardSummary:
    total_returns = [result.total_return_pct for result in window_results]
    return WalkForwardSummary(
        account_name=account_name,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        window_count=len(window_results),
        run_ids=[result.run_id for result in window_results],
        average_return_pct=sum(total_returns) / len(total_returns),
        median_return_pct=float(median(total_returns)),
        best_return_pct=max(total_returns),
        worst_return_pct=min(total_returns),
    )


def _persist_walk_forward_group(
    conn,
    *,
    cfg,
    summary: WalkForwardSummary,
    window_results: list[_WalkForwardWindowResult],
    insert_group_fn,
    insert_group_run_fn,
    grouping_key_factory,
    commit_fn,
) -> None:
    group_id = insert_group_fn(
        conn,
        primary_run_id=window_results[0].run_id,
        grouping_key=grouping_key_factory(),
        run_name_prefix=_normalized_run_name_prefix(cfg.run_name_prefix),
        start_date=summary.start_date,
        end_date=summary.end_date,
        test_months=cfg.test_months,
        step_months=cfg.step_months,
        window_count=summary.window_count,
        average_return_pct=summary.average_return_pct,
        median_return_pct=summary.median_return_pct,
        best_return_pct=summary.best_return_pct,
        worst_return_pct=summary.worst_return_pct,
    )
    for result in window_results:
        insert_group_run_fn(
            conn,
            group_id=group_id,
            run_id=result.run_id,
            window_index=result.window_index,
            window_start=result.window_start,
            window_end=result.window_end,
            total_return_pct=result.total_return_pct,
        )
    commit_fn(conn)


def _commit_connection(conn) -> None:
    conn.commit()


def _build_grouping_key() -> str:
    return uuid4().hex


def execute_walk_forward_backtest(
    conn,
    *,
    cfg,
    start_date,
    end_date,
    windows: list[tuple],
    run_backtest_fn,
    insert_group_fn=insert_walk_forward_group,
    insert_group_run_fn=insert_walk_forward_group_run,
    grouping_key_factory=_build_grouping_key,
    commit_fn=_commit_connection,
) -> WalkForwardSummary:
    if not windows:
        raise ValueError("No walk-forward windows generated for the selected date range.")

    normalized_prefix = _normalized_run_name_prefix(cfg.run_name_prefix)
    window_results: list[_WalkForwardWindowResult] = []

    for window_index, (window_start, window_end) in enumerate(windows, start=1):
        run_name = _build_window_run_name(
            run_name_prefix=normalized_prefix,
            window_index=window_index,
        )

        test_cfg = BacktestConfig(
            account_name=cfg.account_name,
            tickers_file=cfg.tickers_file,
            universe_history_dir=cfg.universe_history_dir,
            start=window_start.isoformat(),
            end=window_end.isoformat(),
            lookback_months=None,
            slippage_bps=cfg.slippage_bps,
            fee_per_trade=cfg.fee_per_trade,
            run_name=run_name,
            allow_approximate_leaps=cfg.allow_approximate_leaps,
        )

        result = run_backtest_fn(conn, test_cfg)
        window_results.append(
            _WalkForwardWindowResult(
                run_id=result.run_id,
                window_index=window_index,
                window_start=window_start.isoformat(),
                window_end=window_end.isoformat(),
                total_return_pct=result.total_return_pct,
            )
        )

    if not window_results:
        raise ValueError("No returns were computed.")

    summary = _build_walk_forward_summary(
        account_name=cfg.account_name,
        start_date=start_date,
        end_date=end_date,
        window_results=window_results,
    )
    _persist_walk_forward_group(
        conn,
        cfg=cfg,
        summary=summary,
        window_results=window_results,
        insert_group_fn=insert_group_fn,
        insert_group_run_fn=insert_group_run_fn,
        grouping_key_factory=grouping_key_factory,
        commit_fn=commit_fn,
    )
    return summary
