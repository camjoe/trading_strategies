"""Evaluation queries for evaluation consumers.

Owns caller-facing strategy evaluation reads beneath the stable
``trading.services.evaluation`` package surface.
"""

from __future__ import annotations

import sqlite3

from backtesting.services.evidence import build_strategy_evidence
from common.time import utc_now_iso
from trading.models import AccountRecord
from trading.models.evaluation import EvaluationMeta, StrategyEvaluationArtifact
from trading.services.accounts.mutations import get_account
from trading.services.evaluation.evidence import (
    build_basic_scope,
    build_confidence,
    build_diagnostics,
    build_paper_live_evidence,
    resolve_active_strategy,
    resolve_requested_strategy,
)
from trading.services.operational_settings.queries import fetch_evaluation_confidence_settings


def fetch_strategy_evaluation_for_account_row(
    conn: sqlite3.Connection,
    account: AccountRecord,
    *,
    strategy_name: str | None = None,
) -> StrategyEvaluationArtifact:
    # Resolved once and threaded: the scope, the requested-strategy fallback, and
    # the paper-live window all need the account's active strategy.
    active_strategy = resolve_active_strategy(conn, account)
    requested_strategy = resolve_requested_strategy(strategy_name, active_strategy=active_strategy)
    account_id = account.id
    basic = build_basic_scope(conn, account, requested_strategy, active_strategy=active_strategy)
    backtest, walk_forward = build_strategy_evidence(
        conn,
        account_id=account_id,
        requested_strategy=requested_strategy,
    )
    paper_live = build_paper_live_evidence(
        conn,
        account=account,
        requested_strategy=requested_strategy,
        active_strategy=active_strategy,
    )
    confidence_settings = fetch_evaluation_confidence_settings(conn)
    confidence = build_confidence(
        backtest=backtest,
        paper_live=paper_live,
        settings=confidence_settings,
    )
    generated_at = utc_now_iso()
    diagnostics = build_diagnostics(
        backtest=backtest,
        paper_live=paper_live,
        walk_forward=walk_forward,
        generated_at=generated_at,
    )
    return StrategyEvaluationArtifact(
        meta=EvaluationMeta(generated_at=generated_at),
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
    account = get_account(conn, account_name)
    return fetch_strategy_evaluation_for_account_row(
        conn,
        account,
        strategy_name=strategy_name,
    )
