from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import Mapping, cast

from common.coercion import row_expect_int, row_expect_str, row_float, row_int, row_str
from common.time import utc_now_iso
from trading.backtesting.domain.metrics import max_drawdown_pct
from trading.backtesting.repositories.report_repository import (
    fetch_backtest_report_run,
    fetch_backtest_report_snapshots,
    fetch_backtest_report_trades,
    fetch_latest_backtest_run_id_for_account_strategy,
)
from trading.backtesting.repositories.walk_forward_repository import (
    fetch_latest_walk_forward_group_for_account_strategy,
    fetch_walk_forward_group_runs,
)
from trading.domain.evaluation_confidence import (
    compute_backtest_confidence,
    compute_blended_score,
    compute_overall_confidence,
    compute_paper_live_confidence,
)
from trading.domain.evaluation_models import (
    EvaluationBacktestEvidence,
    EvaluationBasicScope,
    EvaluationConfidence,
    EvaluationDiagnostics,
    EvaluationMeta,
    EvaluationPaperLiveEvidence,
    EvaluationWalkForwardEvidence,
    StrategyEvaluationArtifact,
)
from trading.domain.returns import safe_return_pct
from trading.domain.rotation import resolve_active_strategy
from trading.repositories.accounts_repository import fetch_account_by_name
from trading.repositories.rotation_repository import (
    fetch_latest_closed_rotation_episode,
    fetch_open_rotation_episode,
)
from trading.repositories.snapshots_repository import (
    fetch_latest_snapshot_details_row,
    fetch_snapshot_count_between,
    fetch_snapshot_count_for_account,
)

# Current non-broker-managed evaluation evidence mode for standard accounts.
PAPER_EVIDENCE_MODE = "paper"

# Evaluation mode label for accounts explicitly enabled for live broker trading.
LIVE_EVIDENCE_MODE = "live"

# Account-wide snapshot evidence is only strategy-safe for non-rotating accounts.
ACCOUNT_SNAPSHOT_SOURCE_LEVEL = "account_snapshot"

# Open rotation episodes give strategy-isolated in-flight evidence for the active strategy.
OPEN_ROTATION_EPISODE_SOURCE_LEVEL = "rotation_episode_open"

# Closed rotation episodes give strategy-isolated historical evidence for inactive strategies.
CLOSED_ROTATION_EPISODE_SOURCE_LEVEL = "rotation_episode_closed"

# Diagnostics key used when no strategy-matched backtest rows are persisted.
BACKTEST_EVIDENCE_GAP = "missing_backtest_evidence"

# Diagnostics key used when no strategy-safe paper/live rows are persisted.
PAPER_LIVE_EVIDENCE_GAP = "missing_paper_live_evidence"

# Diagnostics key used when no grouped walk-forward evidence is persisted.
WALK_FORWARD_EVIDENCE_GAP = "walk_forward_grouping_not_persisted"


def _resolve_requested_strategy(account: sqlite3.Row, strategy_name: str | None) -> str:
    if strategy_name is not None:
        normalized = strategy_name.strip()
        if normalized:
            return normalized
    return resolve_active_strategy(cast(Mapping[str, object], account))


def _build_basic_scope(account: sqlite3.Row, requested_strategy: str) -> EvaluationBasicScope:
    return EvaluationBasicScope(
        account_id=row_expect_int(account, "id"),
        account_name=row_expect_str(account, "name"),
        descriptive_name=row_str(account, "descriptive_name"),
        requested_strategy=requested_strategy,
        base_strategy=row_expect_str(account, "strategy"),
        active_strategy=resolve_active_strategy(cast(Mapping[str, object], account)),
        benchmark_ticker=row_expect_str(account, "benchmark_ticker"),
        instrument_mode=row_str(account, "instrument_mode"),
        rotation_enabled=bool(row_int(account, "rotation_enabled")),
        live_trading_enabled=bool(row_int(account, "live_trading_enabled")),
    )


def _build_backtest_evidence(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    requested_strategy: str,
) -> EvaluationBacktestEvidence:
    run_id = fetch_latest_backtest_run_id_for_account_strategy(
        conn,
        account_id=account_id,
        strategy_name=requested_strategy,
    )
    if run_id is None:
        return EvaluationBacktestEvidence()

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


def _evidence_mode(account: sqlite3.Row) -> str:
    return LIVE_EVIDENCE_MODE if bool(row_int(account, "live_trading_enabled")) else PAPER_EVIDENCE_MODE


def _latest_rotation_episode_evidence(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    requested_strategy: str,
    latest_snapshot: sqlite3.Row | None,
) -> EvaluationPaperLiveEvidence:
    open_episode = fetch_open_rotation_episode(conn, account_id=account_id)
    if (
        open_episode is not None
        and latest_snapshot is not None
        and row_str(open_episode, "strategy_name") == requested_strategy
    ):
        started_at = row_expect_str(open_episode, "started_at")
        latest_snapshot_time = row_expect_str(latest_snapshot, "snapshot_time")
        snapshot_count = fetch_snapshot_count_between(
            conn,
            account_id=account_id,
            start_iso=started_at,
            end_iso=latest_snapshot_time,
        )
        starting_equity = row_float(open_episode, "starting_equity")
        latest_equity = row_float(latest_snapshot, "equity")
        return EvaluationPaperLiveEvidence(
            available=True,
            source_level=OPEN_ROTATION_EPISODE_SOURCE_LEVEL,
            strategy_isolated=True,
            latest_snapshot_time=latest_snapshot_time,
            snapshot_count=snapshot_count,
            starting_equity=starting_equity,
            latest_equity=latest_equity,
            return_pct=safe_return_pct(starting_equity, latest_equity),
            cash=row_float(latest_snapshot, "cash"),
            market_value=row_float(latest_snapshot, "market_value"),
            realized_pnl=row_float(latest_snapshot, "realized_pnl"),
            unrealized_pnl=row_float(latest_snapshot, "unrealized_pnl"),
            rotation_episode_id=row_int(open_episode, "id"),
            episode_started_at=started_at,
            episode_realized_pnl_delta=None,
        )

    closed_episode = fetch_latest_closed_rotation_episode(
        conn,
        account_id=account_id,
        strategy_name=requested_strategy,
    )
    if closed_episode is None:
        return EvaluationPaperLiveEvidence()

    starting_equity = row_float(closed_episode, "starting_equity")
    ending_equity = row_float(closed_episode, "ending_equity")
    return EvaluationPaperLiveEvidence(
        available=True,
        source_level=CLOSED_ROTATION_EPISODE_SOURCE_LEVEL,
        strategy_isolated=True,
        latest_snapshot_time=row_str(closed_episode, "ended_at"),
        snapshot_count=row_int(closed_episode, "snapshot_count"),
        starting_equity=starting_equity,
        latest_equity=ending_equity,
        return_pct=safe_return_pct(starting_equity, ending_equity),
        realized_pnl=row_float(closed_episode, "ending_realized_pnl"),
        rotation_episode_id=row_int(closed_episode, "id"),
        episode_started_at=row_str(closed_episode, "started_at"),
        episode_ended_at=row_str(closed_episode, "ended_at"),
        episode_realized_pnl_delta=row_float(closed_episode, "realized_pnl_delta"),
    )


def _build_paper_live_evidence(
    conn: sqlite3.Connection,
    *,
    account: sqlite3.Row,
    requested_strategy: str,
) -> EvaluationPaperLiveEvidence:
    account_id = row_expect_int(account, "id")
    latest_snapshot = fetch_latest_snapshot_details_row(conn, account_id=account_id)
    evidence = _latest_rotation_episode_evidence(
        conn,
        account_id=account_id,
        requested_strategy=requested_strategy,
        latest_snapshot=latest_snapshot,
    ) if bool(row_int(account, "rotation_enabled")) else EvaluationPaperLiveEvidence()
    if evidence.available:
        return replace(evidence, mode=_evidence_mode(account))

    if latest_snapshot is None or bool(row_int(account, "rotation_enabled")):
        return EvaluationPaperLiveEvidence(mode=_evidence_mode(account))

    latest_equity = row_float(latest_snapshot, "equity")
    return EvaluationPaperLiveEvidence(
        available=True,
        mode=_evidence_mode(account),
        source_level=ACCOUNT_SNAPSHOT_SOURCE_LEVEL,
        strategy_isolated=True,
        latest_snapshot_time=row_str(latest_snapshot, "snapshot_time"),
        snapshot_count=fetch_snapshot_count_for_account(conn, account_id=account_id),
        starting_equity=row_float(account, "initial_cash"),
        latest_equity=latest_equity,
        return_pct=safe_return_pct(row_float(account, "initial_cash"), latest_equity),
        cash=row_float(latest_snapshot, "cash"),
        market_value=row_float(latest_snapshot, "market_value"),
        realized_pnl=row_float(latest_snapshot, "realized_pnl"),
        unrealized_pnl=row_float(latest_snapshot, "unrealized_pnl"),
    )


def _build_walk_forward_evidence(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    requested_strategy: str,
) -> EvaluationWalkForwardEvidence:
    group = fetch_latest_walk_forward_group_for_account_strategy(
        conn,
        account_id=account_id,
        strategy_name=requested_strategy,
    )
    if group is None:
        return EvaluationWalkForwardEvidence()

    group_runs = fetch_walk_forward_group_runs(
        conn,
        group_id=row_expect_int(group, "id"),
    )
    return EvaluationWalkForwardEvidence(
        available=bool(group_runs),
        grouped=bool(group_runs),
        run_ids=[row_expect_int(item, "run_id") for item in group_runs],
        average_return_pct=row_float(group, "average_return_pct"),
        median_return_pct=row_float(group, "median_return_pct"),
        best_return_pct=row_float(group, "best_return_pct"),
        worst_return_pct=row_float(group, "worst_return_pct"),
    )


def _build_confidence(
    *,
    backtest: EvaluationBacktestEvidence,
    paper_live: EvaluationPaperLiveEvidence,
) -> EvaluationConfidence:
    backtest_confidence = compute_backtest_confidence(
        trade_count=backtest.trade_count,
        snapshot_count=backtest.snapshot_count,
    )
    paper_live_confidence = compute_paper_live_confidence(
        snapshot_count=paper_live.snapshot_count,
    )
    return EvaluationConfidence(
        backtest_confidence=backtest_confidence,
        paper_live_confidence=paper_live_confidence,
        overall_confidence=compute_overall_confidence(
            backtest_confidence=backtest_confidence,
            paper_live_confidence=paper_live_confidence,
        ),
        blended_score=compute_blended_score(
            backtest_score=backtest.total_return_pct,
            paper_live_score=paper_live.return_pct,
            backtest_confidence=backtest_confidence,
            paper_live_confidence=paper_live_confidence,
        ),
    )


def _build_diagnostics(
    *,
    backtest: EvaluationBacktestEvidence,
    paper_live: EvaluationPaperLiveEvidence,
    walk_forward: EvaluationWalkForwardEvidence,
) -> EvaluationDiagnostics:
    data_gaps: list[str] = []
    if not backtest.available:
        data_gaps.append(BACKTEST_EVIDENCE_GAP)
    if not paper_live.available:
        data_gaps.append(PAPER_LIVE_EVIDENCE_GAP)
    if not walk_forward.available:
        data_gaps.append(WALK_FORWARD_EVIDENCE_GAP)
    return EvaluationDiagnostics(data_gaps=data_gaps)


def fetch_strategy_evaluation_for_account_row(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    *,
    strategy_name: str | None = None,
) -> StrategyEvaluationArtifact:
    requested_strategy = _resolve_requested_strategy(account, strategy_name)
    account_id = row_expect_int(account, "id")
    basic = _build_basic_scope(account, requested_strategy)
    backtest = _build_backtest_evidence(
        conn,
        account_id=account_id,
        requested_strategy=requested_strategy,
    )
    paper_live = _build_paper_live_evidence(
        conn,
        account=account,
        requested_strategy=requested_strategy,
    )
    walk_forward = _build_walk_forward_evidence(
        conn,
        account_id=account_id,
        requested_strategy=requested_strategy,
    )
    confidence = _build_confidence(
        backtest=backtest,
        paper_live=paper_live,
    )
    diagnostics = _build_diagnostics(
        backtest=backtest,
        paper_live=paper_live,
        walk_forward=walk_forward,
    )
    return StrategyEvaluationArtifact(
        meta=EvaluationMeta(generated_at=utc_now_iso()),
        basic=basic,
        backtest=backtest,
        walk_forward=walk_forward,
        paper_live=paper_live,
        confidence=confidence,
        diagnostics=diagnostics,
    )


def fetch_strategy_evaluation(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
) -> StrategyEvaluationArtifact:
    account = fetch_account_by_name(conn, account_name)
    if account is None:
        raise ValueError(f"Account '{account_name}' not found.")
    return fetch_strategy_evaluation_for_account_row(
        conn,
        account,
        strategy_name=strategy_name,
    )
