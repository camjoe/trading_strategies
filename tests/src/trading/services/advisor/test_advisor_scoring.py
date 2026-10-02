from __future__ import annotations

from datetime import date

import pytest

from backtesting.models.backtest import BacktestConfig, BacktestResult
from tests.support.backtesting import make_backtest_result
from trading.domain.exceptions import ValidationError
from trading.models.advisor import (
    DECIDED_BY_AGENT,
    DECISION_TYPE_DISABLE_STRATEGY,
    DECISION_TYPE_HOLD,
    DECISION_TYPE_RUN_EXPERIMENT,
    OUTCOME_STATUS_INCONCLUSIVE,
    OUTCOME_STATUS_MEASURED,
    OUTCOME_STATUS_PENDING,
    StrategyDecisionInsert,
)
from trading.repositories.books import BookRepository
from trading.repositories.strategy_decisions import StrategyDecisionRepository
from trading.services.accounts.mutations import create_account, get_account
from trading.services.advisor.decisions import record_decision
from trading.services.advisor.scoring import score_due_decisions
from trading.services.strategy_catalog.mutations import create_strategy_variant

_ACCOUNT = "advisor_scoring"
# The decision date and a scoring date well past its 21-trading-day window.
_DECIDED_AT = "2026-08-03T15:00:00Z"
_AS_OF = date(2026, 10, 1)

# Backtest return per arm, keyed by the fast_window knob the scorer passes from the catalog row.
_ARM_RETURNS = {5: 6.0, 30: 2.0}


class _FakeBacktests:
    """Records each arm's config; returns a total return keyed by the arm's fast_window knob."""

    def __init__(self, *, fail: bool = False) -> None:
        self.configs: list[BacktestConfig] = []
        self.fail = fail

    def __call__(self, _conn, cfg: BacktestConfig) -> BacktestResult:
        self.configs.append(cfg)
        if self.fail:
            raise ValueError("Not enough historical bars in selected range.")
        fast_window = int((cfg.param_override or {}).get("fast_window", 0))
        return make_backtest_result(
            cfg.account_name,
            total_return_pct=_ARM_RETURNS.get(fast_window, 0.0),
            benchmark_return_pct=3.0,
        )


@pytest.fixture
def account(conn):
    create_account(conn, _ACCOUNT, "trend", 10_000.0, "SPY")
    create_strategy_variant(conn, strategy_key="trend_fast", primitive="trend", params={"fast_window": 5})
    create_strategy_variant(conn, strategy_key="trend_slow", primitive="trend", params={"fast_window": 30})
    return get_account(conn, _ACCOUNT)


def _strategy_id(conn, key: str) -> int:
    return int(conn.execute("SELECT id FROM strategies WHERE strategy_key = ?", (key,)).fetchone()["id"])


def _due_decision(conn, account, *, decision_type: str, chosen: str | None, alternative: str | None) -> int:
    book = BookRepository(conn).fetch_default_for_account(account_id=account.id)
    return StrategyDecisionRepository(conn).insert(
        StrategyDecisionInsert(
            account_id=account.id,
            book_id=book.id,
            strategy_id=_strategy_id(conn, chosen) if chosen else None,
            alternative_strategy_id=_strategy_id(conn, alternative) if alternative else None,
            decision_type=decision_type,
            rationale="test decision",
            evidence_json="{}",
            decided_by=DECIDED_BY_AGENT,
            created_at=_DECIDED_AT,
        )
    )


def _outcome(conn, decision_id: int):
    record = StrategyDecisionRepository(conn).fetch(strategy_decision_id=decision_id)
    assert record is not None
    return record.outcome


@pytest.mark.parametrize(
    ("chosen", "alternative", "verdict"),
    [
        ("trend_fast", "trend_slow", "helped"),  # 6.0 vs 2.0
        ("trend_slow", "trend_fast", "hurt"),  # 2.0 vs 6.0
    ],
)
def test_scores_the_chosen_arm_against_the_rejected_one(conn, account, chosen, alternative, verdict) -> None:
    decision_id = _due_decision(
        conn, account, decision_type=DECISION_TYPE_HOLD, chosen=chosen, alternative=alternative
    )

    results = score_due_decisions(conn, run_backtest_fn=_FakeBacktests(), as_of=_AS_OF)

    outcome = _outcome(conn, decision_id)
    assert [result.strategy_decision_id for result in results] == [decision_id]
    assert outcome.outcome_status == OUTCOME_STATUS_MEASURED
    assert outcome.outcome_verdict == verdict
    assert outcome.realized_benchmark_return_pct == 3.0
    assert outcome.outcome_note == f"chosen {chosen} vs rejected {alternative}"


def test_each_arm_runs_with_its_catalog_knobs_not_the_primitive_defaults(conn, account) -> None:
    _due_decision(conn, account, decision_type=DECISION_TYPE_HOLD, chosen="trend_fast", alternative="trend_slow")
    backtests = _FakeBacktests()

    score_due_decisions(conn, run_backtest_fn=backtests, as_of=_AS_OF)

    assert {cfg.strategy for cfg in backtests.configs} == {"trend"}
    assert sorted(cfg.param_override["fast_window"] for cfg in backtests.configs) == [5, 30]
    first = backtests.configs[0]
    assert (first.start, first.warmup_months) == ("2026-08-03", 6)
    # Both arms trade the book's own universe.
    assert len({cfg.tickers_file for cfg in backtests.configs}) == 1


def test_a_disabled_strategy_is_scored_against_cash(conn, account) -> None:
    decision_id = _due_decision(
        conn, account, decision_type=DECISION_TYPE_DISABLE_STRATEGY, chosen="trend_fast", alternative=None
    )

    score_due_decisions(conn, run_backtest_fn=_FakeBacktests(), as_of=_AS_OF)

    outcome = _outcome(conn, decision_id)
    # Disabling a strategy that went on to return 6% hurt: cash returned 0%.
    assert (outcome.chosen_return_pct, outcome.alternative_return_pct) == (0.0, 6.0)
    assert outcome.outcome_verdict == "hurt"


@pytest.mark.parametrize(
    ("decision_type", "alternative", "reason"),
    [
        (DECISION_TYPE_HOLD, None, "no rejected alternative"),
        (DECISION_TYPE_RUN_EXPERIMENT, None, "run_experiment"),
    ],
)
def test_unscorable_decisions_are_inconclusive_with_the_reason(
    conn, account, decision_type, alternative, reason
) -> None:
    decision_id = _due_decision(
        conn, account, decision_type=decision_type, chosen="trend_fast", alternative=alternative
    )

    score_due_decisions(conn, run_backtest_fn=_FakeBacktests(), as_of=_AS_OF)

    outcome = _outcome(conn, decision_id)
    assert outcome.outcome_status == OUTCOME_STATUS_INCONCLUSIVE
    assert reason in (outcome.outcome_note or "")
    assert outcome.outcome_verdict is None


def test_a_failed_backtest_is_inconclusive_not_an_error(conn, account) -> None:
    decision_id = _due_decision(
        conn, account, decision_type=DECISION_TYPE_HOLD, chosen="trend_fast", alternative="trend_slow"
    )

    score_due_decisions(conn, run_backtest_fn=_FakeBacktests(fail=True), as_of=_AS_OF)

    outcome = _outcome(conn, decision_id)
    assert outcome.outcome_status == OUTCOME_STATUS_INCONCLUSIVE
    assert "backtest failed" in (outcome.outcome_note or "")


def test_a_decision_still_inside_its_window_stays_pending(conn, account) -> None:
    decision_id = _due_decision(
        conn, account, decision_type=DECISION_TYPE_HOLD, chosen="trend_fast", alternative="trend_slow"
    )

    results = score_due_decisions(conn, run_backtest_fn=_FakeBacktests(), as_of=date(2026, 8, 10))

    assert results == []
    assert _outcome(conn, decision_id).outcome_status == OUTCOME_STATUS_PENDING


def test_scored_decisions_leave_the_pending_queue(conn, account) -> None:
    _due_decision(conn, account, decision_type=DECISION_TYPE_HOLD, chosen="trend_fast", alternative="trend_slow")
    score_due_decisions(conn, run_backtest_fn=_FakeBacktests(), as_of=_AS_OF)

    assert score_due_decisions(conn, run_backtest_fn=_FakeBacktests(), as_of=_AS_OF) == []


class TestRecordAlternative:
    def test_stores_the_rejected_alternative(self, conn, account) -> None:
        decision_id = record_decision(
            conn,
            account_name=_ACCOUNT,
            decision_type=DECISION_TYPE_HOLD,
            rationale="incumbent still leads",
            decided_by=DECIDED_BY_AGENT,
            strategy_key="trend_fast",
            alternative_strategy_key="trend_slow",
        )
        record = StrategyDecisionRepository(conn).fetch(strategy_decision_id=decision_id)
        assert record is not None
        assert record.alternative_strategy_id == _strategy_id(conn, "trend_slow")

    @pytest.mark.parametrize(
        ("decision_type", "chosen", "alternative", "message"),
        [
            (DECISION_TYPE_DISABLE_STRATEGY, "trend_fast", "trend_slow", "takes no alternative"),
            (DECISION_TYPE_RUN_EXPERIMENT, "trend_fast", "trend_slow", "takes no alternative"),
            (DECISION_TYPE_HOLD, "trend_fast", "trend_fast", "must differ"),
        ],
    )
    def test_rejects_an_invalid_alternative(self, conn, account, decision_type, chosen, alternative, message) -> None:
        with pytest.raises(ValidationError, match=message):
            record_decision(
                conn,
                account_name=_ACCOUNT,
                decision_type=decision_type,
                rationale="r",
                decided_by=DECIDED_BY_AGENT,
                strategy_key=chosen,
                alternative_strategy_key=alternative,
            )
