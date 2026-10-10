"""Build the advisor scorecard from scored ledger decisions."""

from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from trading.domain.advisor_scorecard import build_scorecard_groups, find_leader
from trading.domain.exceptions import ValidationError
from trading.models.advisor import SCORECARD_GROUP_AGENT, SCORECARD_GROUPS, Scorecard
from trading.repositories.strategy_decisions import StrategyDecisionRepository
from trading.services.accounts.mutations import get_account


def build_advisor_scorecard(
    conn: sqlite3.Connection,
    *,
    account_name: str | None = None,
    group_by: str = SCORECARD_GROUP_AGENT,
) -> Scorecard:
    """The track record of scored decisions, grouped by agent, decision type, or regime.

    Read-only. Covers every scored decision (measured or inconclusive) for one account, or
    for all accounts when ``account_name`` is None.
    """
    if group_by not in SCORECARD_GROUPS:
        raise ValidationError(f"Unknown scorecard grouping '{group_by}'. Valid: {', '.join(SCORECARD_GROUPS)}")
    account_id = get_account(conn, account_name).id if account_name is not None else None
    groups = build_scorecard_groups(
        StrategyDecisionRepository(conn).fetch_scored(account_id=account_id),
        group_by=group_by,
    )
    return Scorecard(
        generated_at=utc_now_iso(),
        group_by=group_by,
        groups=groups,
        rankable_count=sum(1 for group in groups if group.rankable),
        leader=find_leader(groups),
    )
