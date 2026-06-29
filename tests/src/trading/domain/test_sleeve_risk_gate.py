from __future__ import annotations

import pytest

from trading.domain.sleeve_risk_gate import evaluate_sleeve_risk_gate, resolve_sector_for_symbol
from trading.models.sleeves.sleeve_position_record import SleevePositionRecord
from trading.models.sleeves.sleeve_risk_gate_config import SleeveRiskGateConfig
from trading.models.sleeves.sleeve_trade_intent import SleeveTradeIntent


def _intent(*, sleeve_id: int, side: str, symbol: str, qty: int, price: float) -> SleeveTradeIntent:
    return SleeveTradeIntent(
        account_id=1,
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=None,
        side=side,
        symbol=symbol,
        qty=qty,
        requested_price=price,
        forced_sell=None,
        delta_est=None,
        iv_est=None,
    )


def _position(*, sleeve_id: int, symbol: str, market_value: float) -> SleevePositionRecord:
    return SleevePositionRecord(
        sleeve_id=sleeve_id,
        symbol=symbol,
        qty=1.0,
        avg_cost=market_value,
        market_value=market_value,
        unrealized_pnl=0.0,
        updated_at="2026-05-03T14:00:00Z",
    )


def test_allows_buy_within_limits() -> None:
    result = evaluate_sleeve_risk_gate(
        intents=[_intent(sleeve_id=1, side="buy", symbol="AAPL", qty=1, price=100.0)],
        sleeve_equity_by_id={1: 1_000.0},
        positions=[],
    )

    assert result.allowed_count == 1
    assert result.rescaled_count == 0
    assert result.blocked_count == 0
    assert result.approved_intents[0].qty == 1
    assert result.decisions[0].action == "allow"


def test_rescales_by_sleeve_notional_cap() -> None:
    # Sleeve equity 1_000 * default 0.25 cap = 250 notional ceiling => 2 shares at 100.
    result = evaluate_sleeve_risk_gate(
        intents=[_intent(sleeve_id=1, side="buy", symbol="AAPL", qty=5, price=100.0)],
        sleeve_equity_by_id={1: 1_000.0},
        positions=[],
    )

    assert result.rescaled_count == 1
    assert result.approved_intents[0].qty == 2
    decision = result.decisions[0]
    assert decision.action == "rescale"
    assert decision.approved_qty == 2
    assert decision.reason_code == "sleeve_notional_cap"


def test_blocks_when_gross_exposure_is_exhausted() -> None:
    result = evaluate_sleeve_risk_gate(
        intents=[_intent(sleeve_id=1, side="buy", symbol="AAPL", qty=1, price=100.0)],
        sleeve_equity_by_id={1: 1_000.0},
        positions=[_position(sleeve_id=1, symbol="MSFT", market_value=1_000.0)],
    )

    assert result.blocked_count == 1
    assert result.approved_intents == []
    assert result.decisions[0].action == "block"
    assert result.decisions[0].reason_code == "gross_exposure_cap"


def test_sell_is_allowed_and_reduces_gross_exposure() -> None:
    result = evaluate_sleeve_risk_gate(
        intents=[_intent(sleeve_id=1, side="sell", symbol="AAPL", qty=1, price=100.0)],
        sleeve_equity_by_id={1: 1_000.0},
        positions=[_position(sleeve_id=1, symbol="AAPL", market_value=100.0)],
    )

    assert result.allowed_count == 1
    assert result.decisions[0].reason_code == "risk_reducing_sell"
    assert result.gross_exposure_after < result.gross_exposure_before


def test_blocks_non_positive_qty() -> None:
    result = evaluate_sleeve_risk_gate(
        intents=[_intent(sleeve_id=1, side="buy", symbol="AAPL", qty=0, price=100.0)],
        sleeve_equity_by_id={1: 1_000.0},
        positions=[],
    )

    assert result.blocked_count == 1
    assert result.decisions[0].reason_code == "non_positive_qty"


def test_empty_intents_returns_empty_result() -> None:
    result = evaluate_sleeve_risk_gate(
        intents=[],
        sleeve_equity_by_id={1: 1_000.0},
        positions=[],
    )

    assert result.decisions == []
    assert result.approved_intents == []
    assert result.allowed_count == 0


def test_non_positive_config_is_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_sleeve_risk_gate(
            intents=[_intent(sleeve_id=1, side="buy", symbol="AAPL", qty=1, price=100.0)],
            sleeve_equity_by_id={1: 1_000.0},
            positions=[],
            config=SleeveRiskGateConfig(max_sleeve_notional_pct=0.0),
        )


def test_resolve_sector_for_symbol_ignores_blank_mappings() -> None:
    assert resolve_sector_for_symbol("AAPL", symbol_sector_map={"AAPL": "   "}) is None
    assert resolve_sector_for_symbol("MSFT", symbol_sector_map={}) is None
    assert resolve_sector_for_symbol("aapl", symbol_sector_map={"AAPL": "Technology"}) == "technology"
