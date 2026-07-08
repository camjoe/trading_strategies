"""Book-keyed champion/challenger rotation selection for accounts.

Routes a plain account's rotation *selection* through the same decision-score
champion/challenger model the sleeve path uses. Given the account's default book,
the incumbent (its active strategy) and challengers (its rotation schedule) are
enumerated on the decision-score contract (2b-2), then the shared book-keyed
rotation core (``evaluate_book_rotation``) picks the winner and records the decision
on the default book's ``rotation_decisions``.

Cadence (2b-4b): the interval/schedule trigger (``is_rotation_due``) stays the "when"
in ``rotate_account_if_due``; on top of it the account now shares the same per-book
**cooldown guard** as sleeves, so a fresh rotation cannot churn within the cooldown
window. This owns the "what" (which strategy); applying the winner to account state
stays in ``rotate_account_if_due``.
"""

from __future__ import annotations

import sqlite3

from common.coercion import row_expect_int
from trading.domain.rotation import parse_rotation_schedule, resolve_active_strategy
from trading.models import AccountRecord
from trading.repositories.book_bridge import default_book_id
from trading.repositories.strategy_param_sets import StrategyParamSetRepository
from trading.services.auto_trading.rotation_candidates import build_book_rotation_candidates
from trading.services.sleeves.rotation import (
    SleeveRotationConfig,
    book_cooldown_active,
    evaluate_book_rotation,
)


def evaluate_account_rotation_decision(
    conn: sqlite3.Connection,
    account: AccountRecord,
    as_of_iso: str,
    *,
    config: SleeveRotationConfig = SleeveRotationConfig(),
) -> str | None:
    """Select the account's rotation strategy via champion/challenger and record it.

    Returns the selected strategy (the winning challenger on ``rotate``, the
    incumbent on ``hold``), or ``None`` when there is no active strategy to treat as
    the incumbent. A decision row is written on the account's default book whenever
    an incumbent exists — the audit of the hold/rotate call.
    """
    incumbent_strategy = resolve_active_strategy(account)
    if not incumbent_strategy:
        return None

    schedule = [name for name in parse_rotation_schedule(account["rotation_schedule"]) if name]
    book_id = default_book_id(conn, row_expect_int(account, "id"))

    param_set_repo = StrategyParamSetRepository(conn)
    incumbent_param_set = param_set_repo.fetch_active(strategy_name=incumbent_strategy)
    candidates = build_book_rotation_candidates(
        conn,
        book_id=book_id,
        account=account,
        incumbent_strategy=incumbent_strategy,
        incumbent_param_set_id=incumbent_param_set.id if incumbent_param_set is not None else None,
        schedule=schedule,
    )

    cooldown_active = book_cooldown_active(
        conn,
        book_id=book_id,
        decision_time=as_of_iso,
        cooldown_days=config.cooldown_days,
    )
    decision, _decision_id = evaluate_book_rotation(
        conn,
        book_id=book_id,
        incumbent=candidates.incumbent,
        challengers=candidates.challengers,
        config=config,
        cooldown_active=cooldown_active,
        decision_time=as_of_iso,
    )
    return decision.selected_strategy
