from __future__ import annotations

import pytest

from trading.domain.risk_gate import (
    evaluate_risk_gate,
    point_in_time_drawdown_pct,
    resolve_sector_for_symbol,
)
from trading.models.execution import BookTradeCandidate, RiskGateConfig, RiskGatePosition


def _intent(
    *, book_id: int, side: str, symbol: str, qty: float, price: float, quantity_step: float = 1.0
) -> BookTradeCandidate:
    return BookTradeCandidate(
        account_id=1,
        book_id=book_id,
        strategy_name="trend",
        side=side,
        symbol=symbol,
        qty=qty,
        requested_price=price,
        forced_sell=None,
        delta_est=None,
        iv_est=None,
        quantity_step=quantity_step,
    )


def _position(*, book_id: int, symbol: str, market_value: float) -> RiskGatePosition:
    return RiskGatePosition(
        book_id=book_id,
        symbol=symbol,
        qty=1.0,
        avg_cost=market_value,
        market_value=market_value,
        unrealized_pnl=0.0,
        updated_at="2026-05-03T14:00:00Z",
    )


def test_allows_buy_within_limits() -> None:
    result = evaluate_risk_gate(
        intents=[_intent(book_id=1, side="buy", symbol="AAPL", qty=1, price=100.0)],
        book_equity_by_id={1: 1_000.0},
        positions=[],
    )

    assert result.allowed_count == 1
    assert result.rescaled_count == 0
    assert result.blocked_count == 0
    assert result.approved_intents[0].qty == 1
    assert result.decisions[0].action == "allow"


def test_rescales_by_book_notional_cap() -> None:
    # Book equity 1_000 * default 0.25 cap = 250 notional ceiling => 2 shares at 100.
    result = evaluate_risk_gate(
        intents=[_intent(book_id=1, side="buy", symbol="AAPL", qty=5, price=100.0)],
        book_equity_by_id={1: 1_000.0},
        positions=[],
    )

    assert result.rescaled_count == 1
    assert result.approved_intents[0].qty == 2
    decision = result.decisions[0]
    assert decision.action == "rescale"
    assert decision.approved_qty == 2
    assert decision.reason_code == "book_notional_cap"


_FRACTIONAL_STEP = 1.0 / 1_000_000


def test_allows_fractional_buy_within_limits() -> None:
    # 0.6 shares at 100 = 60 notional, well inside the 0.25 * 10_000 book cap.
    result = evaluate_risk_gate(
        intents=[
            _intent(book_id=1, side="buy", symbol="AAPL", qty=0.6, price=100.0, quantity_step=_FRACTIONAL_STEP)
        ],
        book_equity_by_id={1: 10_000.0},
        positions=[],
    )

    assert result.allowed_count == 1
    assert result.approved_intents[0].qty == pytest.approx(0.6)
    assert result.decisions[0].action == "allow"


def test_rescales_a_fractional_buy_to_the_step_not_a_whole_share() -> None:
    # Book equity 1_000 * 0.25 = 250 notional ceiling => 2.5 shares at 100, kept
    # fractional. A whole-share floor would drop it to 2.
    result = evaluate_risk_gate(
        intents=[_intent(book_id=1, side="buy", symbol="AAPL", qty=5, price=100.0, quantity_step=_FRACTIONAL_STEP)],
        book_equity_by_id={1: 1_000.0},
        positions=[],
    )

    assert result.rescaled_count == 1
    assert result.approved_intents[0].qty == pytest.approx(2.5)
    assert result.decisions[0].action == "rescale"


def test_rescaled_fractional_buy_below_one_share_is_not_blocked() -> None:
    # Cap room is 60 notional at a 100 price — less than one share. The whole-unit
    # floor blocked this outright; the fractional step approves 0.6 shares.
    result = evaluate_risk_gate(
        intents=[_intent(book_id=1, side="buy", symbol="AAPL", qty=5, price=100.0, quantity_step=_FRACTIONAL_STEP)],
        book_equity_by_id={1: 240.0},
        positions=[],
    )

    assert result.blocked_count == 0
    assert result.rescaled_count == 1
    assert result.approved_intents[0].qty == pytest.approx(0.6)


def test_blocks_when_gross_exposure_is_exhausted() -> None:
    result = evaluate_risk_gate(
        intents=[_intent(book_id=1, side="buy", symbol="AAPL", qty=1, price=100.0)],
        book_equity_by_id={1: 1_000.0},
        positions=[_position(book_id=1, symbol="MSFT", market_value=1_000.0)],
    )

    assert result.blocked_count == 1
    assert result.approved_intents == []
    assert result.decisions[0].action == "block"
    assert result.decisions[0].reason_code == "gross_exposure_cap"


def test_sell_is_allowed_and_reduces_gross_exposure() -> None:
    result = evaluate_risk_gate(
        intents=[_intent(book_id=1, side="sell", symbol="AAPL", qty=1, price=100.0)],
        book_equity_by_id={1: 1_000.0},
        positions=[_position(book_id=1, symbol="AAPL", market_value=100.0)],
    )

    assert result.allowed_count == 1
    assert result.decisions[0].reason_code == "risk_reducing_sell"
    assert result.gross_exposure_after < result.gross_exposure_before


def test_blocks_non_positive_qty() -> None:
    result = evaluate_risk_gate(
        intents=[_intent(book_id=1, side="buy", symbol="AAPL", qty=0, price=100.0)],
        book_equity_by_id={1: 1_000.0},
        positions=[],
    )

    assert result.blocked_count == 1
    assert result.decisions[0].reason_code == "non_positive_qty"


def test_empty_intents_returns_empty_result() -> None:
    result = evaluate_risk_gate(
        intents=[],
        book_equity_by_id={1: 1_000.0},
        positions=[],
    )

    assert result.decisions == []
    assert result.approved_intents == []
    assert result.allowed_count == 0


def test_non_positive_config_is_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_risk_gate(
            intents=[_intent(book_id=1, side="buy", symbol="AAPL", qty=1, price=100.0)],
            book_equity_by_id={1: 1_000.0},
            positions=[],
            config=RiskGateConfig(max_book_notional_pct=0.0),
        )


def test_tied_caps_report_the_broadest_constraint() -> None:
    """An account pinned on several caps must not read as one book's own limit."""
    result = evaluate_risk_gate(
        intents=[_intent(book_id=1, side="buy", symbol="AAPL", qty=1, price=100.0)],
        book_equity_by_id={1: 1_000.0},
        # 1_000 of MSFT exhausts both gross (1.0x equity) and technology (45%),
        # so those two tie at exactly 0.0 while symbol and book still have room.
        positions=[_position(book_id=1, symbol="MSFT", market_value=1_000.0)],
        config=RiskGateConfig(symbol_sector_map={"AAPL": "technology", "MSFT": "technology"}),
    )

    assert result.blocked_count == 1
    assert result.decisions[0].reason_code == "sector_concentration_cap"


def test_drawdown_breaker_blocks_buys() -> None:
    result = evaluate_risk_gate(
        intents=[_intent(book_id=1, side="buy", symbol="AAPL", qty=1, price=100.0)],
        book_equity_by_id={1: 1_000.0},
        positions=[],
        drawdown_pct=-25.0,
    )

    assert result.blocked_count == 1
    assert result.approved_intents == []
    assert result.decisions[0].reason_code == "drawdown_breaker"


def test_drawdown_breaker_still_allows_sells() -> None:
    """The point of blocking buys rather than halting: an exit must stay open."""
    result = evaluate_risk_gate(
        intents=[
            _intent(book_id=1, side="sell", symbol="AAPL", qty=1, price=100.0),
            _intent(book_id=1, side="buy", symbol="MSFT", qty=1, price=100.0),
        ],
        book_equity_by_id={1: 1_000.0},
        positions=[_position(book_id=1, symbol="AAPL", market_value=100.0)],
        drawdown_pct=-25.0,
    )

    assert [decision.reason_code for decision in result.decisions] == ["risk_reducing_sell", "drawdown_breaker"]
    assert [intent.symbol for intent in result.approved_intents] == ["AAPL"]


def test_drawdown_breaker_trips_exactly_at_the_limit() -> None:
    shallower = evaluate_risk_gate(
        intents=[_intent(book_id=1, side="buy", symbol="AAPL", qty=1, price=100.0)],
        book_equity_by_id={1: 1_000.0},
        positions=[],
        drawdown_pct=-19.99,
    )
    at_limit = evaluate_risk_gate(
        intents=[_intent(book_id=1, side="buy", symbol="AAPL", qty=1, price=100.0)],
        book_equity_by_id={1: 1_000.0},
        positions=[],
        drawdown_pct=-20.0,
    )

    assert shallower.allowed_count == 1
    assert at_limit.blocked_count == 1


def test_drawdown_breaker_is_off_without_equity_history() -> None:
    """No snapshots means no measurable peak — not a breach."""
    result = evaluate_risk_gate(
        intents=[_intent(book_id=1, side="buy", symbol="AAPL", qty=1, price=100.0)],
        book_equity_by_id={1: 1_000.0},
        positions=[],
        drawdown_pct=None,
    )

    assert result.allowed_count == 1


def test_point_in_time_drawdown_pct() -> None:
    assert point_in_time_drawdown_pct(total_equity=800.0, peak_equity=1_000.0) == pytest.approx(-20.0)
    # A new high reads as flat, not positive.
    assert point_in_time_drawdown_pct(total_equity=1_200.0, peak_equity=1_000.0) == pytest.approx(0.0)
    assert point_in_time_drawdown_pct(total_equity=1_000.0, peak_equity=None) == pytest.approx(0.0)
    assert point_in_time_drawdown_pct(total_equity=0.0, peak_equity=1_000.0) is None


def test_resolve_sector_for_symbol_ignores_blank_mappings() -> None:
    assert resolve_sector_for_symbol("AAPL", symbol_sector_map={"AAPL": "   "}) is None
    assert resolve_sector_for_symbol("MSFT", symbol_sector_map={}) is None
    assert resolve_sector_for_symbol("aapl", symbol_sector_map={"AAPL": "Technology"}) == "technology"
