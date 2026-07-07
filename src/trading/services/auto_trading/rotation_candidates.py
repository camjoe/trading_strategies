"""Book-keyed rotation candidate enumeration.

Given a book's incumbent strategy and a candidate schedule, produces the incumbent +
challenger candidates scored on the **decision-score contract** — the input the
champion/challenger rotation policy compares. This is the single enumeration used by
both a plain account (its default book) and a sleeve (its bridging book); the caller
resolves the incumbent + schedule for the book, and the per-strategy metrics come
from the shared decision-score builder.

Generalizes the sleeve-only `build_sleeve_shadow_evaluation`. The candidate metrics
type is reused from the sleeve model for now (it is book-agnostic strategy data; the
P5 naming pass renames `SleeveStrategyMetrics` → a book-neutral name).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from trading.models import AccountRecord
from trading.models.sleeves.sleeve_strategy_metrics import SleeveStrategyMetrics
from trading.repositories.strategy_param_sets import StrategyParamSetRepository
from trading.services.sleeves.shadow_evaluation import build_sleeve_metrics_from_evaluation


@dataclass(frozen=True, slots=True)
class BookRotationCandidates:
    """The incumbent + challenger candidates for one book, scored by decision score."""

    book_id: int
    incumbent_strategy: str
    incumbent: SleeveStrategyMetrics
    challengers: list[SleeveStrategyMetrics]


def build_book_rotation_candidates(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    account: AccountRecord,
    incumbent_strategy: str,
    incumbent_param_set_id: int | None,
    schedule: Sequence[str],
) -> BookRotationCandidates:
    """Enumerate a book's rotation candidates (incumbent + challengers) with decision scores.

    ``schedule`` is the candidate strategy list (the account's rotation schedule).
    Each challenger is scored with its active param set; the incumbent keeps the
    book's assigned param set. Both are scored through the same decision-score source,
    so the champion/challenger comparison is apples-to-apples.
    """
    incumbent = build_sleeve_metrics_from_evaluation(
        conn,
        account=account,
        strategy_name=incumbent_strategy,
        param_set_id=incumbent_param_set_id,
    )
    param_set_repo = StrategyParamSetRepository(conn)
    challengers: list[SleeveStrategyMetrics] = []
    for strategy_name in schedule:
        if strategy_name == incumbent_strategy:
            continue
        active_param_set = param_set_repo.fetch_active(strategy_name=strategy_name)
        challengers.append(
            build_sleeve_metrics_from_evaluation(
                conn,
                account=account,
                strategy_name=strategy_name,
                param_set_id=active_param_set.id if active_param_set is not None else None,
            )
        )
    return BookRotationCandidates(
        book_id=book_id,
        incumbent_strategy=incumbent_strategy,
        incumbent=incumbent,
        challengers=challengers,
    )
