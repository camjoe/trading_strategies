from __future__ import annotations

from tests.support.books import (
    assign_test_book_strategy,
    insert_test_book,
    set_test_book_rotation_scheduling,
)
from tests.support.repositories import insert_repository_account
from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationConfidence,
    StrategyEvaluationArtifact,
)
from trading.services.accounts.mutations import get_account
from trading.services.books.rotation.challenger_evaluation import build_book_challenger_evaluations

# rotation_metrics resolves the evaluation fetch lazily (the one deliberate
# books -> evaluation back-edge), so patch it on the evaluation package.
_FETCH_TARGET = "trading.services.evaluation.queries.fetch_strategy_evaluation_for_account_row"


def _artifact(*, blended_score: float | None, trade_count: int, available: bool = True) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        backtest=EvaluationBacktestEvidence(available=available, trade_count=trade_count),
        confidence=EvaluationConfidence(blended_score=blended_score, overall_confidence=0.3),
    )


def test_build_book_challenger_evaluations_builds_incumbent_and_challengers(conn, monkeypatch) -> None:
    account_name = "acct_shadow_eval"
    account_id = insert_repository_account(conn, name=account_name)
    book_id = insert_test_book(conn, account_id=account_id, name="core")
    assign_test_book_strategy(conn, book_id=book_id, strategy_name="trend")
    set_test_book_rotation_scheduling(
        conn,
        book_id=book_id,
        enabled=1,
        schedule=["trend", "meanrev", "breakout"],
        lookback_days=45,
    )
    account = get_account(conn, account_name)

    scores = {"trend": 1.0, "meanrev": 2.0, "breakout": 0.5}
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(blended_score=scores[strategy_name], trade_count=5),
    )

    result = build_book_challenger_evaluations(
        conn,
        account=account,
        as_of_iso="2026-05-07T12:00:00Z",
    )

    assert result.account_name == account_name
    assert len(result.books) == 1
    book = result.books[0]
    assert book.book_id == book_id
    assert book.incumbent_strategy == "trend"
    assert book.incumbent.strategy_name == "trend"
    assert book.incumbent.risk_adjusted_return == 1.0
    assert [item.strategy_name for item in book.challengers] == ["meanrev", "breakout"]
    assert [item.risk_adjusted_return for item in book.challengers] == [2.0, 0.5]
    assert all(item.trade_count == 5 for item in book.challengers)
    # The evidence window comes from the book's own lookback.
    assert book.rolling_window_days == 45
    assert book.window_end_day == "2026-05-07"


def test_disabled_or_unconfigured_books_are_skipped(conn, monkeypatch) -> None:
    account_id = insert_repository_account(conn, name="acct_shadow_gate")
    disabled = insert_test_book(conn, account_id=account_id, name="disabled")
    assign_test_book_strategy(conn, book_id=disabled, strategy_name="trend")
    set_test_book_rotation_scheduling(conn, book_id=disabled, enabled=0, schedule=["trend", "meanrev"])
    no_settings_row = insert_test_book(conn, account_id=account_id, name="unconfigured")
    assign_test_book_strategy(conn, book_id=no_settings_row, strategy_name="trend")
    account = get_account(conn, "acct_shadow_gate")

    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(blended_score=1.0, trade_count=5),
    )

    result = build_book_challenger_evaluations(conn, account=account, as_of_iso="2026-05-07T12:00:00Z")

    # Disabled book and missing-settings book (code default: disabled) skipped.
    assert result.books == []


def test_explicit_window_overrides_book_lookback(conn, monkeypatch) -> None:
    account_id = insert_repository_account(conn, name="acct_shadow_override")
    book_id = insert_test_book(conn, account_id=account_id, name="core")
    assign_test_book_strategy(conn, book_id=book_id, strategy_name="trend")
    set_test_book_rotation_scheduling(conn, book_id=book_id, enabled=1, schedule=["trend"], lookback_days=90)
    account = get_account(conn, "acct_shadow_override")

    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(blended_score=1.0, trade_count=5),
    )

    result = build_book_challenger_evaluations(
        conn,
        account=account,
        as_of_iso="2026-05-07T12:00:00Z",
        rolling_window_days=10,
    )

    assert result.books[0].rolling_window_days == 10
