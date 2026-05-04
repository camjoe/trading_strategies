from __future__ import annotations

from trading.repositories.sleeve_positions import upsert_sleeve_position
from trading.repositories.sleeves import insert_strategy_sleeve
from trading.services.sleeves.execution import SleeveTradeIntent
from trading.services.sleeves.risk_gate import evaluate_sleeve_risk_gate
from tests.support.repositories import insert_repository_account


def _insert_sleeve(conn, *, account_id: int, sleeve_id: int, equity: float) -> int:
    return insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name=f"sleeve_{sleeve_id}",
        status="active",
        base_ccy="USD",
        start_equity=equity,
        current_cash=equity,
        current_equity=equity,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
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
    upsert_sleeve_position(
        conn,
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
    upsert_sleeve_position(
        conn,
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
