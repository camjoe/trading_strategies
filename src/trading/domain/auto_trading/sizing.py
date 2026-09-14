"""Buy and sell sizing — how large a signalled trade the book funds.

Sizing rounds down to a tradeable increment, ``quantity_step``. The default is
whole shares (``WHOLE_SHARE_STEP``), which the backtest and options/leaps use;
the live equity path passes ``FRACTIONAL_SHARE_STEP`` so it can size fractional
shares at the storage precision.
"""

import math
from collections.abc import Sequence

from common.constants import QUANTITY_MINOR_UNITS_PER_SHARE

# Default account-level buy sizing controls. Percent fields in this repository
# are stored as 0-100 values, not 0-1 fractions.
DEFAULT_TRADE_SIZE_PCT = 10.0
DEFAULT_MAX_POSITION_PCT = 20.0

# The tradeable share increment sizing rounds down to. Whole shares is the
# default; the fractional step is the smallest storable share fraction.
WHOLE_SHARE_STEP = 1.0
FRACTIONAL_SHARE_STEP = 1.0 / QUANTITY_MINOR_UNITS_PER_SHARE


def _truncate_to_step(quantity: float, step: float) -> float:
    """The largest multiple of ``step`` not exceeding ``quantity`` (never negative)."""
    if quantity <= 0 or step <= 0:
        return 0.0
    return math.floor(quantity / step) * step


def _resolve_sizing_pct(value: float | None, *, default: float, field_name: str) -> float:
    if value is None:
        return default
    pct = float(value)
    if pct <= 0 or pct > 100:
        raise ValueError(f"{field_name} must be greater than 0 and <= 100.")
    return pct


def choose_buy_qty(
    cash: float,
    price: float,
    fee: float,
    *,
    trade_size_pct: float | None = None,
    max_position_pct: float | None = None,
    current_position_value: float = 0.0,
    portfolio_equity: float | None = None,
    quantity_step: float = WHOLE_SHARE_STEP,
) -> float:
    if price <= 0:
        return 0.0

    resolved_trade_size_pct = _resolve_sizing_pct(
        trade_size_pct,
        default=DEFAULT_TRADE_SIZE_PCT,
        field_name="trade_size_pct",
    )
    resolved_max_position_pct = _resolve_sizing_pct(
        max_position_pct,
        default=DEFAULT_MAX_POSITION_PCT,
        field_name="max_position_pct",
    )
    if resolved_trade_size_pct > resolved_max_position_pct:
        raise ValueError("trade_size_pct cannot be greater than max_position_pct.")

    effective_equity = float(portfolio_equity) if portfolio_equity is not None else float(cash)
    if effective_equity <= 0 or cash <= fee:
        return 0.0

    trade_budget = effective_equity * (resolved_trade_size_pct / 100.0)
    position_cap = effective_equity * (resolved_max_position_pct / 100.0)
    remaining_position_budget = max(0.0, position_cap - max(0.0, float(current_position_value)))
    spendable_budget = min(max(0.0, cash - fee), trade_budget, remaining_position_budget)
    return _truncate_to_step(spendable_budget / price, quantity_step)


def allocate_buy_quantities(
    sized_buys: Sequence[tuple[str, float, float]],
    *,
    cash: float,
    fee_per_trade: float,
    quantity_step: float = WHOLE_SHARE_STEP,
) -> dict[str, float]:
    """Fund one bar's buy signals, scaling proportionally when cash cannot cover them all.

    *sized_buys* is ``(ticker, execution_price, requested_qty)`` per signaled
    ticker, already sized by :func:`choose_buy_qty` against the book's policy.
    Returns the quantity actually funded per ticker, omitting any that cannot
    afford one ``quantity_step``.

    A buy signal carries no conviction — every "buy" on a bar is equally
    preferred, because that is all the strategy said. So when cash binds, the
    engine must not invent a preference between them. Funding requests one at a
    time in list order silently hands the cash to whichever tickers happen to
    come first, which is a property of the iteration order rather than of the
    strategy; sorted input makes that the alphabet. Proportional scaling is the
    allocation that asserts no ordering, and it is order-independent by
    construction: each ticker's share depends only on its own request and the
    total.

    When the requests fit, every ticker gets exactly what it asked for and this
    is a no-op. Rounding to ``quantity_step`` can leave a little cash unspent;
    that is left uninvested rather than handed to an arbitrary winner.
    """
    requests = [(ticker, price, qty) for ticker, price, qty in sized_buys if qty >= quantity_step and price > 0]
    if not requests:
        return {}

    costs = {ticker: (qty * price) + fee_per_trade for ticker, price, qty in requests}
    total_cost = sum(costs.values())
    if total_cost <= cash:
        return {ticker: qty for ticker, _price, qty in requests}

    granted: dict[str, float] = {}
    for ticker, price, requested_qty in requests:
        share = cash * (costs[ticker] / total_cost)
        spendable = share - fee_per_trade
        affordable = min(_truncate_to_step(spendable / price, quantity_step), requested_qty)
        if affordable >= quantity_step:
            granted[ticker] = affordable
    return granted


def closing_sell_qty(position_qty: float, *, quantity_step: float = WHOLE_SHARE_STEP) -> float:
    """The quantity that closes the position outright, rounded down to ``quantity_step``."""
    return _truncate_to_step(position_qty, quantity_step)
