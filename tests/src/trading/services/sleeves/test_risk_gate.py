from __future__ import annotations

import pytest

from trading.models.sleeves.sleeve_risk_gate_config import SleeveRiskGateConfig
from trading.models.sleeves.sleeve_trade_intent import SleeveTradeIntent
from trading.repositories.sleeve_positions import SleevePositionRepository
from trading.services.sleeves.risk_gate import evaluate_sleeve_risk_gate
from tests.support.repositories import insert_repository_account
from tests.support.sleeves import insert_test_sleeve


def _insert_sleeve(conn, *, account_id: int, sleeve_id: int, equity: float) -> int:
    return insert_test_sleeve(
        conn,
        account_id=account_id,
        name=f"sleeve_{sleeve_id}",
        start_equity=equity,
        current_cash=equity,
        current_equity=equity,
    )


def test_evaluate_sleeve_risk_gate_allows_buy_within_limits(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_risk_allow")
    sleeve_id = _insert_sleeve(conn, account_id=account_id, sleeve_id=1, equity=1_000.0)
    intent = SleeveTradeIntent(
        account_id=account_id,
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=None,
        side="buy",
        symbol="AAPL",
        qty=1,
        requested_price=100.0,
        forced_sell=None,
        delta_est=None,
        iv_est=None,
    )

    result = evaluate_sleeve_risk_gate(conn, account_id=account_id, intents=[intent])
    assert len(result.approved_intents) == 1
    assert result.approved_intents[0].qty == 1
    assert result.allowed_count == 1
    assert result.rescaled_count == 0
    assert result.blocked_count == 0
    assert result.decisions[0].action == "allow"


def test_evaluate_sleeve_risk_gate_rescales_by_sleeve_cap(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_risk_rescale")
    sleeve_id = _insert_sleeve(conn, account_id=account_id, sleeve_id=2, equity=1_000.0)
    intent = SleeveTradeIntent(
        account_id=account_id,
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=None,
        side="buy",
        symbol="AAPL",
        qty=5,
        requested_price=100.0,
        forced_sell=None,
        delta_est=None,
        iv_est=None,
    )

    result = evaluate_sleeve_risk_gate(conn, account_id=account_id, intents=[intent])
    assert len(result.approved_intents) == 1
    assert result.approved_intents[0].qty == 2
    assert result.allowed_count == 0
    assert result.rescaled_count == 1
    assert result.blocked_count == 0
    assert result.decisions[0].action == "rescale"
    assert result.decisions[0].reason_code == "sleeve_notional_cap"


def test_evaluate_sleeve_risk_gate_blocks_when_gross_exposure_is_exhausted(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_risk_block")
    sleeve_a = _insert_sleeve(conn, account_id=account_id, sleeve_id=3, equity=1_000.0)
    _insert_sleeve(conn, account_id=account_id, sleeve_id=4, equity=1_000.0)
    SleevePositionRepository(conn).upsert(
        sleeve_id=sleeve_a,
        symbol="SPY",
        qty=10.0,
        avg_cost=200.0,
        market_value=2_000.0,
        unrealized_pnl=0.0,
        updated_at="2026-05-03T00:00:00Z",
    )
    intent = SleeveTradeIntent(
        account_id=account_id,
        sleeve_id=sleeve_a,
        strategy_name="trend",
        param_set_id=None,
        side="buy",
        symbol="AAPL",
        qty=1,
        requested_price=100.0,
        forced_sell=None,
        delta_est=None,
        iv_est=None,
    )

    result = evaluate_sleeve_risk_gate(conn, account_id=account_id, intents=[intent])
    assert len(result.approved_intents) == 0
    assert result.allowed_count == 0
    assert result.rescaled_count == 0
    assert result.blocked_count == 1
    assert result.decisions[0].action == "block"
    assert result.decisions[0].reason_code == "gross_exposure_cap"


def test_evaluate_sleeve_risk_gate_blocks_when_sector_cap_is_exhausted(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_risk_sector_block")
    sleeve_a = _insert_sleeve(conn, account_id=account_id, sleeve_id=5, equity=1_000.0)
    sleeve_b = _insert_sleeve(conn, account_id=account_id, sleeve_id=6, equity=1_000.0)
    SleevePositionRepository(conn).upsert(
        sleeve_id=sleeve_a,
        symbol="AAPL",
        qty=9.0,
        avg_cost=100.0,
        market_value=900.0,
        unrealized_pnl=0.0,
        updated_at="2026-05-03T00:00:00Z",
    )
    intent = SleeveTradeIntent(
        account_id=account_id,
        sleeve_id=sleeve_b,
        strategy_name="trend",
        param_set_id=None,
        side="buy",
        symbol="MSFT",
        qty=2,
        requested_price=100.0,
        forced_sell=None,
        delta_est=None,
        iv_est=None,
    )

    result = evaluate_sleeve_risk_gate(conn, account_id=account_id, intents=[intent])
    assert len(result.approved_intents) == 0
    assert result.blocked_count == 1
    assert result.decisions[0].action == "block"
    assert result.decisions[0].reason_code == "sector_concentration_cap"


def test_evaluate_sleeve_risk_gate_returns_empty_result_for_no_intents(conn) -> None:
    result = evaluate_sleeve_risk_gate(conn, account_id=1, intents=[])

    assert result.approved_intents == []
    assert result.decisions == []
    assert result.allowed_count == 0
    assert result.rescaled_count == 0
    assert result.blocked_count == 0
    assert result.gross_exposure_before == 0.0
    assert result.gross_exposure_after == 0.0


def test_evaluate_sleeve_risk_gate_rejects_non_positive_config(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_risk_bad_config")
    sleeve_id = _insert_sleeve(conn, account_id=account_id, sleeve_id=7, equity=1_000.0)
    intent = SleeveTradeIntent(
        account_id=account_id,
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=None,
        side="buy",
        symbol="AAPL",
        qty=1,
        requested_price=100.0,
        forced_sell=None,
        delta_est=None,
        iv_est=None,
    )

    with pytest.raises(ValueError, match="max_sleeve_notional_pct must be > 0"):
        evaluate_sleeve_risk_gate(
            conn,
            account_id=account_id,
            intents=[intent],
            config=SleeveRiskGateConfig(max_sleeve_notional_pct=0.0),
        )


def test_evaluate_sleeve_risk_gate_blocks_non_positive_qty(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_risk_non_positive_qty")
    sleeve_id = _insert_sleeve(conn, account_id=account_id, sleeve_id=8, equity=1_000.0)
    intent = SleeveTradeIntent(
        account_id=account_id,
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=None,
        side="buy",
        symbol="AAPL",
        qty=0,
        requested_price=100.0,
        forced_sell=None,
        delta_est=None,
        iv_est=None,
    )

    result = evaluate_sleeve_risk_gate(conn, account_id=account_id, intents=[intent])

    assert result.approved_intents == []
    assert result.blocked_count == 1
    assert result.decisions[0].action == "block"
    assert result.decisions[0].reason_code == "non_positive_qty"
    assert result.decisions[0].approved_qty == 0


def test_evaluate_sleeve_risk_gate_allows_sell_and_reduces_exposure(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_risk_sell")
    sleeve_id = _insert_sleeve(conn, account_id=account_id, sleeve_id=9, equity=1_000.0)
    SleevePositionRepository(conn).upsert(
        sleeve_id=sleeve_id,
        symbol="AAPL",
        qty=3.0,
        avg_cost=100.0,
        market_value=300.0,
        unrealized_pnl=0.0,
        updated_at="2026-05-03T00:00:00Z",
    )
    intent = SleeveTradeIntent(
        account_id=account_id,
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=None,
        side="sell",
        symbol="AAPL",
        qty=2,
        requested_price=100.0,
        forced_sell=None,
        delta_est=None,
        iv_est=None,
    )

    result = evaluate_sleeve_risk_gate(conn, account_id=account_id, intents=[intent])

    assert len(result.approved_intents) == 1
    assert result.allowed_count == 1
    assert result.decisions[0].action == "allow"
    assert result.decisions[0].reason_code == "risk_reducing_sell"
    assert result.gross_exposure_before == 300.0
    assert result.gross_exposure_after == 100.0
