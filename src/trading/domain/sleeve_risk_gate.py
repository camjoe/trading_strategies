"""Pure sleeve risk-gate decision policy — no I/O, no repository calls.

Given a batch of proposed sleeve trade intents plus the current sleeve equity
and position exposures, decide whether each intent is allowed, rescaled to fit a
notional cap, or blocked.  The service layer
(``trading.services.sleeves.risk_gate``) owns the repository reads that build the
inputs.

This mirrors ``trading.domain.rotation_policy.evaluate_champion_challenger_rotation``:
the side-effect-free gate logic lives here and returns a passive
``SleeveRiskGateResult`` value object; the orchestration lives in services.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
import math

from trading.models.sleeves.sleeve_position_record import SleevePositionRecord
from trading.models.sleeves.sleeve_risk_decision import SleeveRiskDecision
from trading.models.sleeves.sleeve_risk_gate_config import SleeveRiskGateConfig
from trading.models.sleeves.sleeve_risk_gate_result import SleeveRiskGateResult
from trading.models.sleeves.sleeve_trade_intent import SleeveTradeIntent


def _coerce_positive_fraction(value: float, *, field_name: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return parsed


def _resolve_blocking_reason(
    *,
    remaining_sleeve_notional: float,
    remaining_symbol_notional: float,
    remaining_gross_notional: float,
    remaining_sector_notional: float,
) -> str:
    limits = [
        ("sleeve_notional_cap", remaining_sleeve_notional),
        ("symbol_concentration_cap", remaining_symbol_notional),
        ("gross_exposure_cap", remaining_gross_notional),
        ("sector_concentration_cap", remaining_sector_notional),
    ]
    limits.sort(key=lambda item: item[1])
    return limits[0][0]


def resolve_sector_for_symbol(symbol: str, *, symbol_sector_map: dict[str, str]) -> str | None:
    normalized_symbol = symbol.upper().strip()
    sector = symbol_sector_map.get(normalized_symbol)
    if sector is None:
        return None
    normalized_sector = sector.strip().lower()
    return normalized_sector if normalized_sector else None


def evaluate_sleeve_risk_gate(
    *,
    intents: Sequence[SleeveTradeIntent],
    sleeve_equity_by_id: Mapping[int, float],
    positions: Sequence[SleevePositionRecord],
    config: SleeveRiskGateConfig = SleeveRiskGateConfig(),
) -> SleeveRiskGateResult:
    if not intents:
        return SleeveRiskGateResult(
            approved_intents=[],
            decisions=[],
            allowed_count=0,
            rescaled_count=0,
            blocked_count=0,
            gross_exposure_before=0.0,
            gross_exposure_after=0.0,
        )

    max_sleeve_notional_pct = _coerce_positive_fraction(
        config.max_sleeve_notional_pct, field_name="max_sleeve_notional_pct"
    )
    max_symbol_concentration_pct = _coerce_positive_fraction(
        config.max_symbol_concentration_pct, field_name="max_symbol_concentration_pct"
    )
    max_portfolio_gross_exposure = _coerce_positive_fraction(
        config.max_portfolio_gross_exposure, field_name="max_portfolio_gross_exposure"
    )
    max_sector_concentration_pct = _coerce_positive_fraction(
        config.max_sector_concentration_pct, field_name="max_sector_concentration_pct"
    )
    symbol_sector_map = {key.upper().strip(): value for key, value in config.symbol_sector_map.items()}

    total_equity = sum(sleeve_equity_by_id.values())
    gross_cap_notional = total_equity * max_portfolio_gross_exposure
    symbol_cap_notional = total_equity * max_symbol_concentration_pct
    sector_cap_notional = total_equity * max_sector_concentration_pct

    symbol_exposure: dict[str, float] = {}
    sector_exposure: dict[str, float] = {}
    sleeve_symbol_exposure: dict[tuple[int, str], float] = {}
    gross_exposure = 0.0
    for pos in positions:
        exposure = abs(pos.market_value)
        gross_exposure += exposure
        symbol_exposure[pos.symbol] = symbol_exposure.get(pos.symbol, 0.0) + exposure
        sector = resolve_sector_for_symbol(pos.symbol, symbol_sector_map=symbol_sector_map)
        if sector is not None:
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + exposure
        sleeve_symbol_exposure[(pos.sleeve_id, pos.symbol)] = exposure
    gross_before = gross_exposure

    approved_intents: list[SleeveTradeIntent] = []
    decisions: list[SleeveRiskDecision] = []
    allowed_count = 0
    rescaled_count = 0
    blocked_count = 0

    for intent in intents:
        side = intent.side.lower().strip()
        symbol = intent.symbol.upper().strip()
        requested_qty = int(intent.qty)
        requested_notional = float(requested_qty) * float(intent.requested_price)
        if requested_qty <= 0:
            blocked_count += 1
            decisions.append(
                SleeveRiskDecision(
                    sleeve_id=int(intent.sleeve_id),
                    symbol=symbol,
                    side=side,
                    action="block",
                    reason_code="non_positive_qty",
                    requested_qty=requested_qty,
                    approved_qty=0,
                    requested_notional=requested_notional,
                    approved_notional=0.0,
                )
            )
            continue

        if side == "sell":
            allowed_count += 1
            approved_intents.append(intent)
            exposure_delta = min(symbol_exposure.get(symbol, 0.0), requested_notional)
            gross_exposure = max(0.0, gross_exposure - exposure_delta)
            symbol_exposure[symbol] = max(0.0, symbol_exposure.get(symbol, 0.0) - exposure_delta)
            sector = resolve_sector_for_symbol(symbol, symbol_sector_map=symbol_sector_map)
            if sector is not None:
                sector_exposure[sector] = max(0.0, sector_exposure.get(sector, 0.0) - exposure_delta)
            sleeve_key = (int(intent.sleeve_id), symbol)
            sleeve_symbol_exposure[sleeve_key] = max(0.0, sleeve_symbol_exposure.get(sleeve_key, 0.0) - exposure_delta)
            decisions.append(
                SleeveRiskDecision(
                    sleeve_id=int(intent.sleeve_id),
                    symbol=symbol,
                    side=side,
                    action="allow",
                    reason_code="risk_reducing_sell",
                    requested_qty=requested_qty,
                    approved_qty=requested_qty,
                    requested_notional=requested_notional,
                    approved_notional=requested_notional,
                )
            )
            continue

        sleeve_equity = sleeve_equity_by_id.get(int(intent.sleeve_id), 0.0)
        sleeve_symbol_cap_notional = sleeve_equity * max_sleeve_notional_pct
        current_sleeve_symbol_exposure = sleeve_symbol_exposure.get((int(intent.sleeve_id), symbol), 0.0)
        remaining_sleeve_notional = max(0.0, sleeve_symbol_cap_notional - current_sleeve_symbol_exposure)
        remaining_symbol_notional = max(0.0, symbol_cap_notional - symbol_exposure.get(symbol, 0.0))
        remaining_gross_notional = max(0.0, gross_cap_notional - gross_exposure)
        sector = resolve_sector_for_symbol(symbol, symbol_sector_map=symbol_sector_map)
        remaining_sector_notional = (
            max(0.0, sector_cap_notional - sector_exposure.get(sector, 0.0)) if sector is not None else float("inf")
        )
        max_notional = min(
            requested_notional,
            remaining_sleeve_notional,
            remaining_symbol_notional,
            remaining_gross_notional,
            remaining_sector_notional,
        )

        price = float(intent.requested_price)
        max_qty = int(math.floor(max_notional / price)) if price > 0 else 0
        if max_qty <= 0:
            blocked_count += 1
            decisions.append(
                SleeveRiskDecision(
                    sleeve_id=int(intent.sleeve_id),
                    symbol=symbol,
                    side=side,
                    action="block",
                    reason_code=_resolve_blocking_reason(
                        remaining_sleeve_notional=remaining_sleeve_notional,
                        remaining_symbol_notional=remaining_symbol_notional,
                        remaining_gross_notional=remaining_gross_notional,
                        remaining_sector_notional=remaining_sector_notional,
                    ),
                    requested_qty=requested_qty,
                    approved_qty=0,
                    requested_notional=requested_notional,
                    approved_notional=0.0,
                )
            )
            continue

        approved_qty = min(requested_qty, max_qty)
        approved_notional = float(approved_qty) * price
        if approved_qty < requested_qty:
            rescaled_count += 1
            action = "rescale"
            reason_code = _resolve_blocking_reason(
                remaining_sleeve_notional=remaining_sleeve_notional,
                remaining_symbol_notional=remaining_symbol_notional,
                remaining_gross_notional=remaining_gross_notional,
                remaining_sector_notional=remaining_sector_notional,
            )
            approved_intents.append(replace(intent, qty=approved_qty))
        else:
            allowed_count += 1
            action = "allow"
            reason_code = "within_limits"
            approved_intents.append(intent)

        gross_exposure += approved_notional
        symbol_exposure[symbol] = symbol_exposure.get(symbol, 0.0) + approved_notional
        if sector is not None:
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + approved_notional
        sleeve_key = (int(intent.sleeve_id), symbol)
        sleeve_symbol_exposure[sleeve_key] = sleeve_symbol_exposure.get(sleeve_key, 0.0) + approved_notional
        decisions.append(
            SleeveRiskDecision(
                sleeve_id=int(intent.sleeve_id),
                symbol=symbol,
                side=side,
                action=action,
                reason_code=reason_code,
                requested_qty=requested_qty,
                approved_qty=approved_qty,
                requested_notional=requested_notional,
                approved_notional=approved_notional,
            )
        )

    return SleeveRiskGateResult(
        approved_intents=approved_intents,
        decisions=decisions,
        allowed_count=allowed_count,
        rescaled_count=rescaled_count,
        blocked_count=blocked_count,
        gross_exposure_before=gross_before,
        gross_exposure_after=gross_exposure,
    )
