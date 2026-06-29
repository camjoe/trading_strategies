"""Sleeve risk-gate orchestration.

Reads current sleeve equity and position exposures from the repositories, then
hands the pure allow/rescale/block decision to
``trading.domain.sleeve_risk_gate.evaluate_sleeve_risk_gate``.

The decision policy, caps, value objects, and sector reference data all live in
the domain/models layers; this module only owns the persistence reads.
"""

from __future__ import annotations

import sqlite3

from trading.domain.sleeve_risk_gate import evaluate_sleeve_risk_gate as evaluate_sleeve_risk_gate_policy
from trading.models.sleeves.sleeve_risk_gate_config import SleeveRiskGateConfig
from trading.models.sleeves.sleeve_risk_gate_result import SleeveRiskGateResult
from trading.models.sleeves.sleeve_trade_intent import SleeveTradeIntent
from trading.repositories.sleeve_positions import SleevePositionRepository
from trading.repositories.sleeves import SleeveRepository
from trading.services.sleeves.sector_config import load_symbol_sector_map


def evaluate_sleeve_risk_gate(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    intents: list[SleeveTradeIntent],
    config: SleeveRiskGateConfig | None = None,
) -> SleeveRiskGateResult:
    if config is None:
        config = SleeveRiskGateConfig(symbol_sector_map=load_symbol_sector_map())
    sleeves = SleeveRepository(conn).fetch_for_account(account_id=int(account_id))
    sleeve_equity_by_id = {s.id: s.current_equity for s in sleeves}
    positions = SleevePositionRepository(conn).fetch_for_account(account_id=int(account_id))
    return evaluate_sleeve_risk_gate_policy(
        intents=intents,
        sleeve_equity_by_id=sleeve_equity_by_id,
        positions=positions,
        config=config,
    )
