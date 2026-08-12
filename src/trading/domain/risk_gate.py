"""Pure book risk-gate decision policy — no I/O, no repository calls.

Given a batch of proposed book trade intents plus the current book equity
and position exposures, decide whether each intent is allowed, rescaled to fit a
notional cap, or blocked.  The service layer
(``trading.services.books.risk_gate``) owns the repository reads that build the
inputs.

This mirrors ``trading.domain.rotation.policy.evaluate_champion_challenger_rotation``:
the side-effect-free gate logic lives here and returns a passive
``RiskGateResult`` value object; the orchestration lives in services.

Rules this gate enforces, and the assumptions behind them:

**Sells are never blocked.** Any ``side == "sell"`` is approved unconditionally as
``risk_reducing_sell`` without consulting a cap. *This is sound only because the
system is long-only*: with no short positions, a sell can only reduce exposure.
If shorting is ever introduced, this branch becomes a hole — a short sale would
increase exposure and pass the gate untouched — and it must be revisited first.
A zero-or-negative quantity is still blocked (``non_positive_qty``) ahead of this
branch, so a sell of nothing does not slip through.

Exposure is summed as ``abs(market_value)``. Under long-only that absolute is a
no-op, but it is deliberate rather than redundant: gross exposure is *defined* as
the absolute sum, so the expression stays correct if short positions are ever
introduced. Do not "simplify" it away — it is one of the few places that would
silently start understating exposure rather than failing loudly.

**Buys are capped four ways**, and the binding constraint is whichever leaves the
least room. The limits are deliberately layered rather than uniform:

* ``max_book_notional_pct`` is **book-scoped** — a share of the intent's own book
  equity.
* ``max_symbol_concentration_pct``, ``max_sector_concentration_pct`` and
  ``max_account_gross_exposure`` are **account-scoped** — shares of
  ``sum(book_equity_by_id.values())``, which the caller populates with one
  account's books.

A book may therefore hold 25% of its own equity in a name that is simultaneously
capped at 30% of the account. Both must pass; neither relaxes the other.

**Nothing here spans accounts.** The gate is evaluated once per account, so two
accounts each sitting at their gross limit are never aggregated. Cross-account
symbol and sector concentration *is* computed — ``services.analysis.concentration``
— but only for operator reporting; it does not gate a trade. Adding a
cross-account tier would mean giving this function account-spanning equity and
position inputs, which it deliberately does not take today.

Note ``sum(book_equity_by_id.values())`` is not an independent quantity: the
runtime calls ``reconcile_book_equity`` immediately before the gate, which halts
the run when the account's rolled-up book equity disagrees with its latest equity
snapshot by more than ``RECONCILIATION_EQUITY_TOLERANCE``. Book-sum equity and
account snapshot equity are therefore the same number, to within a cent, whenever
this code runs.

**An unmapped symbol is bucketed, not exempted.** Sector limits are off entirely
when ``config.symbol_sector_map`` is empty — that is the explicit opt-out. Once a
map is configured, a symbol missing from it is charged to the shared
``UNCATEGORIZED_SECTOR`` bucket and competes for the same sector cap as any other
sector. Missing reference data therefore tightens the gate rather than opening a
hole in it: a ticker added to a trade universe but not to
``infrastructure/config/symbol_sectors.json`` cannot slip the cap.
``scripts/checks/repo/sector_map_check.py`` catches that drift at commit time.

**A drawdown breaker stops buys, not sells.** At or below ``max_drawdown_pct``
under peak equity every buy is blocked as ``drawdown_breaker`` while sells pass
as normal, so a losing account stops adding risk without being trapped in what it
holds. Off when ``drawdown_pct`` is ``None``. Unlike the four caps above,
``max_drawdown_pct`` is a 0-100 percent, matching ``risk_snapshots.drawdown_pct``.

**Intents are evaluated in order and each approval consumes capacity**, so list
order decides who is filled when a cap binds — across books as well as within
one. Both orders are seeded per run date rather than taken from a natural key
(``domain.auto_trading_policy.order_signal_candidates`` for tickers,
``order_capacity_claimants`` for books): stable within a day, varied across days.

Quantities are whole units throughout — ``BookTradeCandidate.qty`` is an ``int``
and the sizing policy filters ``qty >= 1`` before intents reach here.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import replace

from trading.domain.metrics.returns import total_return_pct
from trading.models.execution import (
    BookTradeCandidate,
    RiskGateConfig,
    RiskGateDecision,
    RiskGatePosition,
    RiskGateResult,
)
from trading.models.portfolio import UNCATEGORIZED_SECTOR


def _coerce_positive_fraction(value: float, *, field_name: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return parsed


def _resolve_blocking_reason(
    *,
    remaining_book_notional: float,
    remaining_symbol_notional: float,
    remaining_gross_notional: float,
    remaining_sector_notional: float,
) -> str:
    # These strings are persisted as `risk_decisions.reason_code`, so they stay
    # fixed even where a name has since been sharpened elsewhere:
    # "gross_exposure_cap" is the account-scoped cap now spelled
    # `max_account_gross_exposure`. Renaming it would split the audit history.
    #
    # The sort below is stable, so list order is the tie precedence — and ties are
    # routine, not rare: capacities are floored at 0.0, so an account at two limits
    # produces an exact one. Account-scoped caps lead so a pinned account is not
    # reported as a single book hitting its own limit.
    limits = [
        ("sector_concentration_cap", remaining_sector_notional),
        ("gross_exposure_cap", remaining_gross_notional),
        ("symbol_concentration_cap", remaining_symbol_notional),
        ("book_notional_cap", remaining_book_notional),
    ]
    limits.sort(key=lambda item: item[1])
    return limits[0][0]


def point_in_time_drawdown_pct(*, total_equity: float, peak_equity: float | None) -> float | None:
    """Distance below the account's historical peak equity, in percent (<= 0).

    Account-grain, point-in-time (contrast ``daily_metrics.drawdown_pct``, a
    single-day peak-to-trough figure that needs intraday equity ticks this
    codebase does not persist). ``peak_equity`` includes today's equity so a
    new all-time high reads as 0.0, not a positive number.
    """
    if total_equity <= 0:
        return None
    effective_peak = max(peak_equity, total_equity) if peak_equity is not None else total_equity
    if effective_peak <= 0:
        return None
    return total_return_pct(first_equity=effective_peak, last_equity=total_equity)


def is_drawdown_breaker_tripped(*, drawdown_pct: float | None, max_drawdown_pct: float) -> bool:
    """Whether the account has fallen far enough below peak equity to stop buying.

    ``drawdown_pct`` is signed (0.0 at a high, negative below it) and
    ``max_drawdown_pct`` is the positive limit. ``None`` is not a breach.
    """
    if drawdown_pct is None:
        return False
    return drawdown_pct <= -abs(float(max_drawdown_pct))


def resolve_sector_for_symbol(symbol: str, *, symbol_sector_map: dict[str, str]) -> str | None:
    normalized_symbol = symbol.upper().strip()
    sector = symbol_sector_map.get(normalized_symbol)
    if sector is None:
        return None
    normalized_sector = sector.strip().lower()
    return normalized_sector if normalized_sector else None


def evaluate_risk_gate(
    *,
    intents: Sequence[BookTradeCandidate],
    book_equity_by_id: Mapping[int, float],
    positions: Sequence[RiskGatePosition],
    config: RiskGateConfig = RiskGateConfig(),
    drawdown_pct: float | None = None,
) -> RiskGateResult:
    if not intents:
        return RiskGateResult(
            approved_intents=[],
            decisions=[],
            allowed_count=0,
            rescaled_count=0,
            blocked_count=0,
            gross_exposure_before=0.0,
            gross_exposure_after=0.0,
        )

    max_book_notional_pct = _coerce_positive_fraction(config.max_book_notional_pct, field_name="max_book_notional_pct")
    max_symbol_concentration_pct = _coerce_positive_fraction(
        config.max_symbol_concentration_pct, field_name="max_symbol_concentration_pct"
    )
    max_account_gross_exposure = _coerce_positive_fraction(
        config.max_account_gross_exposure, field_name="max_account_gross_exposure"
    )
    max_sector_concentration_pct = _coerce_positive_fraction(
        config.max_sector_concentration_pct, field_name="max_sector_concentration_pct"
    )
    buys_halted = is_drawdown_breaker_tripped(drawdown_pct=drawdown_pct, max_drawdown_pct=config.max_drawdown_pct)
    symbol_sector_map = {key.upper().strip(): value for key, value in config.symbol_sector_map.items()}
    # No map at all means sector limits are switched off. Once a map exists, an
    # unmapped symbol shares the UNCATEGORIZED_SECTOR bucket instead of escaping
    # the cap, so incomplete reference data cannot open a hole.
    sector_limits_enabled = bool(symbol_sector_map)

    def sector_bucket(candidate_symbol: str) -> str | None:
        if not sector_limits_enabled:
            return None
        return resolve_sector_for_symbol(candidate_symbol, symbol_sector_map=symbol_sector_map) or UNCATEGORIZED_SECTOR

    total_equity = sum(book_equity_by_id.values())
    gross_cap_notional = total_equity * max_account_gross_exposure
    symbol_cap_notional = total_equity * max_symbol_concentration_pct
    sector_cap_notional = total_equity * max_sector_concentration_pct

    symbol_exposure: dict[str, float] = {}
    sector_exposure: dict[str, float] = {}
    book_symbol_exposure: dict[tuple[int, str], float] = {}
    gross_exposure = 0.0
    for pos in positions:
        exposure = abs(pos.market_value)
        gross_exposure += exposure
        symbol_exposure[pos.symbol] = symbol_exposure.get(pos.symbol, 0.0) + exposure
        sector = sector_bucket(pos.symbol)
        if sector is not None:
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + exposure
        book_symbol_exposure[(pos.book_id, pos.symbol)] = exposure
    gross_before = gross_exposure

    approved_intents: list[BookTradeCandidate] = []
    decisions: list[RiskGateDecision] = []
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
                RiskGateDecision(
                    book_id=int(intent.book_id),
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
            sector = sector_bucket(symbol)
            if sector is not None:
                sector_exposure[sector] = max(0.0, sector_exposure.get(sector, 0.0) - exposure_delta)
            book_key = (int(intent.book_id), symbol)
            book_symbol_exposure[book_key] = max(0.0, book_symbol_exposure.get(book_key, 0.0) - exposure_delta)
            decisions.append(
                RiskGateDecision(
                    book_id=int(intent.book_id),
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

        if buys_halted:
            blocked_count += 1
            decisions.append(
                RiskGateDecision(
                    book_id=int(intent.book_id),
                    symbol=symbol,
                    side=side,
                    action="block",
                    reason_code="drawdown_breaker",
                    requested_qty=requested_qty,
                    approved_qty=0,
                    requested_notional=requested_notional,
                    approved_notional=0.0,
                )
            )
            continue

        book_equity = book_equity_by_id.get(int(intent.book_id), 0.0)
        book_symbol_cap_notional = book_equity * max_book_notional_pct
        current_book_symbol_exposure = book_symbol_exposure.get((int(intent.book_id), symbol), 0.0)
        remaining_book_notional = max(0.0, book_symbol_cap_notional - current_book_symbol_exposure)
        remaining_symbol_notional = max(0.0, symbol_cap_notional - symbol_exposure.get(symbol, 0.0))
        remaining_gross_notional = max(0.0, gross_cap_notional - gross_exposure)
        sector = sector_bucket(symbol)
        remaining_sector_notional = (
            max(0.0, sector_cap_notional - sector_exposure.get(sector, 0.0)) if sector is not None else float("inf")
        )
        max_notional = min(
            requested_notional,
            remaining_book_notional,
            remaining_symbol_notional,
            remaining_gross_notional,
            remaining_sector_notional,
        )

        price = float(intent.requested_price)
        max_qty = int(math.floor(max_notional / price)) if price > 0 else 0
        if max_qty <= 0:
            blocked_count += 1
            decisions.append(
                RiskGateDecision(
                    book_id=int(intent.book_id),
                    symbol=symbol,
                    side=side,
                    action="block",
                    reason_code=_resolve_blocking_reason(
                        remaining_book_notional=remaining_book_notional,
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
                remaining_book_notional=remaining_book_notional,
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
        book_key = (int(intent.book_id), symbol)
        book_symbol_exposure[book_key] = book_symbol_exposure.get(book_key, 0.0) + approved_notional
        decisions.append(
            RiskGateDecision(
                book_id=int(intent.book_id),
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

    return RiskGateResult(
        approved_intents=approved_intents,
        decisions=decisions,
        allowed_count=allowed_count,
        rescaled_count=rescaled_count,
        blocked_count=blocked_count,
        gross_exposure_before=gross_before,
        gross_exposure_after=gross_exposure,
    )
