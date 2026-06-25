"""Evaluation queries for evaluation consumers.

Owns caller-facing strategy evaluation reads beneath the stable
``trading.services.evaluation`` package surface.
"""

from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from trading.domain.evaluation_models import EvaluationMeta, StrategyEvaluationArtifact
from trading.models import AccountRecord
from trading.services.accounts import get_account
from trading.services.evaluation.evidence import (
    build_backtest_evidence,
    build_basic_scope,
    build_confidence,
    build_diagnostics,
    build_paper_live_evidence,
    build_walk_forward_evidence,
    resolve_requested_strategy,
)
from trading.services.operational_settings import fetch_evaluation_confidence_settings


def fetch_strategy_evaluation_for_account_row(
    conn: sqlite3.Connection,
    account: AccountRecord,
    *,
    strategy_name: str | None = None,
) -> StrategyEvaluationArtifact:
    requested_strategy = resolve_requested_strategy(account, strategy_name)
    account_id = account.id
    basic = build_basic_scope(account, requested_strategy)
    backtest = build_backtest_evidence(
        conn,
        account_id=account_id,
        requested_strategy=requested_strategy,
    )
    paper_live = build_paper_live_evidence(
        conn,
        account=account,
        requested_strategy=requested_strategy,
    )
    walk_forward = build_walk_forward_evidence(
        conn,
        account_id=account_id,
        requested_strategy=requested_strategy,
    )
    confidence_settings = fetch_evaluation_confidence_settings(conn)
    confidence = build_confidence(
        backtest=backtest,
        paper_live=paper_live,
        settings=confidence_settings,
    )
    diagnostics = build_diagnostics(
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
    account = get_account(conn, account_name)
    return fetch_strategy_evaluation_for_account_row(
        conn,
        account,
        strategy_name=strategy_name,
    )
