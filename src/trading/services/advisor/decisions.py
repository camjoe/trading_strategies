"""Record advisor decisions in the strategy_decisions ledger."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping

from common.time import utc_now_iso
from trading.domain.exceptions import NotFoundError, ValidationError
from trading.models import AccountRecord
from trading.models.advisor import (
    DECISION_TYPE_DISABLE_STRATEGY,
    DECISION_TYPE_RUN_EXPERIMENT,
    DECISION_TYPES,
    DEFAULT_OUTCOME_WINDOW_DAYS,
    StrategyDecisionInsert,
)
from trading.repositories.strategies import StrategyRepository
from trading.repositories.strategy_decisions import StrategyDecisionRepository
from trading.services.accounts.mutations import get_account
from trading.services.books.book_assignments import open_assignment_for_book
from trading.services.books.default_book import fetch_account_book
from trading.services.evaluation.queries import fetch_strategy_evaluation_for_account_row


def record_decision(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    decision_type: str,
    rationale: str,
    decided_by: str,
    book_name: str | None = None,
    strategy_key: str | None = None,
    alternative_strategy_key: str | None = None,
    notes: Mapping[str, object] | None = None,
    optimization_experiment_id: int | None = None,
    promotion_review_id: int | None = None,
    outcome_window_days: int = DEFAULT_OUTCOME_WINDOW_DAYS,
) -> int:
    """Record one decision and return its id.

    The decision is scoped to a book (the account's default book when ``book_name`` is None)
    and a strategy (the book's open assignment when ``strategy_key`` is None): the strategy the
    decision puts or keeps in place. ``alternative_strategy_key`` is the strategy it rejected;
    scoring backtests both over the following window, so a decision recorded without one is
    scored inconclusive. A disabled strategy's alternative is the strategy itself, and
    ``run_experiment`` compares nothing, so neither takes one.

    The evidence is frozen as the strategy's evaluation at this moment plus the caller's
    ``notes``, so the record shows what the system reported when the decision was made.
    """
    _validate_decision_input(
        decision_type=decision_type,
        rationale=rationale,
        decided_by=decided_by,
        outcome_window_days=outcome_window_days,
        has_alternative=alternative_strategy_key is not None,
    )

    account = get_account(conn, account_name)
    book = fetch_account_book(conn, account_name=account_name, book_name=book_name)
    strategy_id, resolved_key = _resolve_strategy(conn, book_id=book.id, strategy_key=strategy_key)
    alternative_strategy_id = _resolve_alternative(conn, alternative_strategy_key, chosen_strategy_id=strategy_id)

    evidence_json = _freeze_evidence(conn, account, strategy_key=resolved_key, notes=notes)

    return StrategyDecisionRepository(conn).insert(
        StrategyDecisionInsert(
            account_id=account.id,
            book_id=book.id,
            strategy_id=strategy_id,
            alternative_strategy_id=alternative_strategy_id,
            decision_type=decision_type,
            rationale=rationale.strip(),
            evidence_json=evidence_json,
            optimization_experiment_id=optimization_experiment_id,
            promotion_review_id=promotion_review_id,
            decided_by=decided_by.strip(),
            created_at=utc_now_iso(),
            outcome_window_days=outcome_window_days,
        )
    )


def _freeze_evidence(
    conn: sqlite3.Connection,
    account: AccountRecord,
    *,
    strategy_key: str | None,
    notes: Mapping[str, object] | None,
) -> str:
    """The strategy's evaluation right now plus the caller's notes, as canonical JSON."""
    evaluation = fetch_strategy_evaluation_for_account_row(conn, account, strategy_name=strategy_key)
    evidence = {"evaluation": evaluation.to_payload(), "notes": dict(notes or {})}
    try:
        return json.dumps(evidence, sort_keys=True)
    except TypeError as error:
        raise ValidationError(f"Decision notes must be JSON-serializable: {error}") from error


def _validate_decision_input(
    *,
    decision_type: str,
    rationale: str,
    decided_by: str,
    outcome_window_days: int,
    has_alternative: bool,
) -> None:
    if decision_type not in DECISION_TYPES:
        raise ValidationError(f"Unknown decision_type '{decision_type}'. Valid: {', '.join(DECISION_TYPES)}")
    if not rationale.strip():
        raise ValidationError("A decision needs a rationale.")
    if not decided_by.strip():
        raise ValidationError("decided_by cannot be empty.")
    if outcome_window_days <= 0:
        raise ValidationError("outcome_window_days must be positive.")
    if has_alternative and decision_type in (
        DECISION_TYPE_DISABLE_STRATEGY,
        DECISION_TYPE_RUN_EXPERIMENT,
    ):
        raise ValidationError(f"A {decision_type} decision takes no alternative strategy.")


def _strategy_id_for_key(conn: sqlite3.Connection, strategy_key: str) -> tuple[int, str]:
    record = StrategyRepository(conn).fetch_by_key(strategy_key=strategy_key.strip().lower())
    if record is None:
        raise NotFoundError(f"No strategy catalog row for '{strategy_key}'.")
    return record.id, record.strategy_key


def _resolve_alternative(
    conn: sqlite3.Connection,
    alternative_strategy_key: str | None,
    *,
    chosen_strategy_id: int | None,
) -> int | None:
    if alternative_strategy_key is None:
        return None
    alternative_id, _ = _strategy_id_for_key(conn, alternative_strategy_key)
    if alternative_id == chosen_strategy_id:
        raise ValidationError("The rejected alternative must differ from the chosen strategy.")
    return alternative_id


def _resolve_strategy(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    strategy_key: str | None,
) -> tuple[int | None, str | None]:
    """The decision's strategy id and key: the named catalog strategy, else the book's assignment."""
    if strategy_key is not None:
        return _strategy_id_for_key(conn, strategy_key)
    assignment = open_assignment_for_book(conn, book_id=book_id)
    if assignment is None:
        return None, None
    return assignment.strategy_id, assignment.strategy_name
