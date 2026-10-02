"""Build the advisor digest: per-account evaluation, ledger state, and review flags."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

from common.time import utc_now_iso
from trading.domain.advisor import build_review_flags, due_for_scoring
from trading.models import AccountRecord
from trading.models.advisor import AdvisorAccountDigest, AdvisorDigest
from trading.repositories.strategy_decisions import StrategyDecisionRepository
from trading.services.accounts.mutations import get_account
from trading.services.accounts.queries import list_account_records
from trading.services.evaluation.queries import fetch_strategy_evaluation_for_account_row

# How many of an account's most recent decisions the digest shows.
RECENT_DECISION_LIMIT = 5


def build_advisor_digest(
    conn: sqlite3.Connection,
    *,
    account_name: str | None = None,
    as_of: date | None = None,
) -> AdvisorDigest:
    """The digest for one account, or every account when ``account_name`` is None.

    Read-only: it composes the existing strategy evaluation with the decision ledger and
    raises review flags. ``as_of`` (default: today, UTC) decides which pending decisions
    are due for scoring.
    """
    as_of_date = as_of or datetime.now(timezone.utc).date()
    accounts = [get_account(conn, account_name)] if account_name is not None else list_account_records(conn)
    return AdvisorDigest(
        generated_at=utc_now_iso(),
        as_of_date=as_of_date.isoformat(),
        accounts=[_account_digest(conn, account, as_of=as_of_date) for account in accounts],
    )


def _account_digest(conn: sqlite3.Connection, account: AccountRecord, *, as_of: date) -> AdvisorAccountDigest:
    repository = StrategyDecisionRepository(conn)
    evaluation = fetch_strategy_evaluation_for_account_row(conn, account)
    due = due_for_scoring(repository.fetch_pending(account_id=account.id), as_of=as_of)
    return AdvisorAccountDigest(
        account_name=account.name,
        evaluation=evaluation,
        recent_decisions=repository.fetch_recent(account_id=account.id, limit=RECENT_DECISION_LIMIT),
        due_decisions=due,
        flags=build_review_flags(evaluation, due_count=len(due)),
    )
