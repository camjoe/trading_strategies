"""Rotation-owned coordination of one account's per-book rotation run.

Sits above ``challenger_evaluation`` (which enumerates each book's incumbent and
challengers) and ``engine`` (which resolves the effective policy and applies the
decision), so callers run an account's rotations through one operation rather
than reproducing the enumerate → resolve-policy → apply sequence themselves.

Lives in its own module because ``challenger_evaluation`` already imports
``engine``; putting the coordinator in either would create an import cycle.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from trading.domain.feature_provider import ExternalFeatureBundle
from trading.models import AccountRecord
from trading.services.books.rotation.challenger_evaluation import build_book_challenger_evaluations
from trading.services.books.rotation.engine import (
    evaluate_and_apply_book_rotation,
    resolve_rotation_policy_config,
)


def run_account_book_rotations(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    decision_time: str,
    fetch_regime: Callable[[str], ExternalFeatureBundle] | None = None,
) -> None:
    """Evaluate and apply the rotation decision for every book in the account.

    ``fetch_regime``, when given, feeds the live market regime into each
    strategy's ``regime_fit`` score component (see
    ``build_rotation_strategy_metrics``); omitted, ``regime_fit`` stays neutral.
    """
    # Scheduling is book-owned (ADR 014): the evaluation resolves each book's
    # enabled gate, challenger schedule, and lookback from its settings row.
    shadow_eval = build_book_challenger_evaluations(
        conn,
        account=account,
        as_of_iso=decision_time,
        fetch_regime=fetch_regime,
    )
    for book_eval in shadow_eval.books:
        # Per-book effective policy: book_rotation_settings overrides with
        # code-default fallback.
        config = resolve_rotation_policy_config(
            conn,
            book_id=book_eval.book_id,
            rolling_window_days=book_eval.rolling_window_days,
            config_version=f"book-rotation:{decision_time[:10]}",
        )
        evaluate_and_apply_book_rotation(
            conn,
            book_id=book_eval.book_id,
            incumbent=book_eval.incumbent,
            challengers=book_eval.challengers,
            config=config,
            decision_time=decision_time,
        )
