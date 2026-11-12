from __future__ import annotations

import json
import sqlite3

import pytest

from trading.domain.accounting.validation import normalize_order_input
from trading.models.execution import RiskGateAction
from trading.models.orders import Side


def test_side_members_are_the_stored_text() -> None:
    assert [side.value for side in Side] == ["buy", "sell"]
    assert Side.BUY == "buy"
    assert Side.SELL == "sell"


def test_risk_gate_action_members_are_the_stored_text() -> None:
    assert {action.value for action in RiskGateAction} == {"allow", "rescale", "block"}
    assert RiskGateAction.BLOCK == "block"


@pytest.mark.parametrize("member", [Side.BUY, RiskGateAction.RESCALE])
def test_members_persist_and_serialize_as_plain_text(member: str) -> None:
    conn = sqlite3.connect(":memory:")
    try:
        stored = conn.execute("SELECT ?", (member,)).fetchone()[0]
    finally:
        conn.close()
    assert type(stored) is str
    assert stored == member.value  # type: ignore[attr-defined]
    assert json.dumps({"value": member}) == json.dumps({"value": stored})
    assert f"{member}" == stored


def test_normalize_order_input_accepts_plain_text_and_members() -> None:
    assert normalize_order_input(" BUY ", "aapl") == ("buy", "AAPL")
    assert normalize_order_input(Side.SELL, "aapl") == ("sell", "AAPL")
    with pytest.raises(ValueError, match="side must be one of: buy, sell"):
        normalize_order_input("short", "aapl")
