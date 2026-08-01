from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from typing import Any, Protocol

from trading.models import AccountState

# ---------------------------------------------------------------------------
# Order sizing
# ---------------------------------------------------------------------------

# Maximum quantity for a single randomized sell order
MAX_ORDER_QTY = 5

# Default account-level buy sizing controls. Percent fields in this repository
# are stored as 0-100 values, not 0-1 fractions.
DEFAULT_TRADE_SIZE_PCT = 10.0
DEFAULT_MAX_POSITION_PCT = 20.0

# ---------------------------------------------------------------------------
# Delta estimation (monotonic strike-offset → delta mapping)
# ---------------------------------------------------------------------------

# Floor and cap keep the estimate in a realistic delta range
DELTA_FLOOR = 0.05
DELTA_CAP = 0.95

# Baseline delta for an at-the-money option (slightly above 0.50 by convention)
DELTA_ATM_ESTIMATE = 0.55

# ---------------------------------------------------------------------------
# Option premium estimation
# ---------------------------------------------------------------------------

# Fallback DTE midpoint (~8 months) when no DTE range is provided by the account
DEFAULT_DTE_MIDPOINT = 240.0

# Bounds on the time-decay factor used in the simplified premium formula
TIME_FACTOR_MIN = 0.08
TIME_FACTOR_MAX = 0.35

# Scales DTE to a [0, 1) range before clamping; chosen so a 1-year DTE (~365 days)
# maps to a time factor of ~0.365 before clamping.
TIME_FACTOR_DTE_SCALE = 1_000.0

# Additive base in the delta-factor component of the premium formula
DELTA_BASE_FACTOR = 0.4

# Minimum option premium in dollars; prevents near-zero or negative estimates
OPTION_PREMIUM_FLOOR = 0.5


class AccountPolicyInput(Protocol):
    def __getitem__(self, key: str) -> Any: ...


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
) -> int:
    if price <= 0:
        return 0

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
        return 0

    trade_budget = effective_equity * (resolved_trade_size_pct / 100.0)
    position_cap = effective_equity * (resolved_max_position_pct / 100.0)
    remaining_position_budget = max(0.0, position_cap - max(0.0, float(current_position_value)))
    spendable_budget = min(max(0.0, cash - fee), trade_budget, remaining_position_budget)
    if spendable_budget < price:
        return 0

    return int(spendable_budget // price)


def allocate_buy_quantities(
    sized_buys: Sequence[tuple[str, float, int]],
    *,
    cash: float,
    fee_per_trade: float,
) -> dict[str, int]:
    """Fund one bar's buy signals, scaling proportionally when cash cannot cover them all.

    *sized_buys* is ``(ticker, execution_price, requested_qty)`` per signaled
    ticker, already sized by :func:`choose_buy_qty` against the book's policy.
    Returns the quantity actually funded per ticker, omitting any that cannot
    afford a single share.

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
    is a no-op. Integer share counts mean the allocation can leave a little cash
    unspent; that is left uninvested rather than handed to an arbitrary winner.
    """
    requests = [(ticker, price, qty) for ticker, price, qty in sized_buys if qty >= 1 and price > 0]
    if not requests:
        return {}

    costs = {ticker: (qty * price) + fee_per_trade for ticker, price, qty in requests}
    total_cost = sum(costs.values())
    if total_cost <= cash:
        return {ticker: qty for ticker, _price, qty in requests}

    granted: dict[str, int] = {}
    for ticker, price, requested_qty in requests:
        share = cash * (costs[ticker] / total_cost)
        spendable = share - fee_per_trade
        if spendable < price:
            continue
        affordable = min(int(spendable // price), requested_qty)
        if affordable >= 1:
            granted[ticker] = affordable
    return granted


def order_signal_candidates(candidates: Sequence[str], *, seed: str) -> list[str]:
    """Order equally-signalled tickers so no name is systematically preferred.

    A run trades one candidate per book, taking the first it can size. The list
    arrives in universe order, so the earliest names in the ticker file were
    always tried first — and since a bought name stops being a buy candidate, a
    book filled up in file order. Every book with the same universe and strategy
    built the same portfolio in the same sequence, for a reason that is a
    property of the file rather than of the market.

    The signal says only "buy", equally, for all of them, so the engine has no
    basis to rank them and must not invent one. Hashing the ticker with a
    per-run *seed* spreads first pick evenly across names over successive runs,
    while staying deterministic within a run: the same seed and candidates
    always yield the same order, so a decision can be reproduced from the audit
    trail rather than merely observed.

    The guarantee is *across runs*, not across books. Callers seed with the run
    date, so every book with the same strategy and universe sees the same order
    on the same day and reaches the same pick. That is intended: two books
    running identical configurations should decide identically, and decorrelating
    them would mean any difference in their results came from this hash rather
    than from what actually differs between them (sizing, equity, risk policy).
    To make two books pick differently, vary something that matters — their
    parameters or their universe.
    """
    return sorted(candidates, key=lambda ticker: hashlib.sha256(f"{seed}:{ticker}".encode()).hexdigest())


def choose_sell_qty(position_qty: float) -> int:
    max_qty = int(position_qty)
    if max_qty < 1:
        return 0
    return random.randint(1, min(MAX_ORDER_QTY, max_qty))


def estimate_delta(abs_strike_offset_pct: float) -> float:
    # Simple monotonic mapping: farther OTM implies lower delta.
    return max(DELTA_FLOOR, min(DELTA_CAP, DELTA_ATM_ESTIMATE - (abs(abs_strike_offset_pct) / 100.0)))


def estimate_option_premium(
    underlying_price: float,
    delta_est: float,
    min_dte: int | None,
    max_dte: int | None,
) -> float:
    dte_mid = DEFAULT_DTE_MIDPOINT
    if min_dte is not None and max_dte is not None:
        dte_mid = (float(min_dte) + float(max_dte)) / 2.0
    elif min_dte is not None:
        dte_mid = float(min_dte)
    elif max_dte is not None:
        dte_mid = float(max_dte)

    time_factor = max(TIME_FACTOR_MIN, min(TIME_FACTOR_MAX, dte_mid / TIME_FACTOR_DTE_SCALE))
    delta_factor = DELTA_BASE_FACTOR + delta_est
    premium = underlying_price * time_factor * delta_factor
    return max(OPTION_PREMIUM_FLOOR, premium)


def option_candidate_allowed(
    account: AccountPolicyInput,
    ticker: str,
    iv_rank_proxy: dict[str, float],
) -> tuple[bool, float, float]:
    strike_offset = float(account["option_strike_offset_pct"] or 0.0)
    delta_est = estimate_delta(strike_offset)
    iv_rank = iv_rank_proxy.get(ticker)

    delta_min = account["target_delta_min"]
    delta_max = account["target_delta_max"]
    if delta_min is not None and delta_est < float(delta_min):
        return False, delta_est, iv_rank if iv_rank is not None else -1.0
    if delta_max is not None and delta_est > float(delta_max):
        return False, delta_est, iv_rank if iv_rank is not None else -1.0

    iv_min = account["iv_rank_min"]
    iv_max = account["iv_rank_max"]
    if (iv_min is not None or iv_max is not None) and iv_rank is None:
        return False, delta_est, -1.0
    if iv_min is not None and iv_rank is not None and iv_rank < float(iv_min):
        return False, delta_est, iv_rank
    if iv_max is not None and iv_rank is not None and iv_rank > float(iv_max):
        return False, delta_est, iv_rank

    return True, delta_est, iv_rank if iv_rank is not None else -1.0


def choose_sell_ticker_by_risk(
    can_sell: list[str],
    prices: dict[str, float],
    state: AccountState,
    risk_policy: str,
    stop_loss_pct: float | None,
    take_profit_pct: float | None,
) -> str | None:
    if not can_sell:
        return None

    candidates: list[str] = []
    for ticker in can_sell:
        price = prices.get(ticker)
        avg_cost = state.avg_cost.get(ticker, 0.0)
        if price is None or price <= 0 or avg_cost <= 0:
            continue

        move_pct = ((price / avg_cost) - 1.0) * 100.0
        if risk_policy in {"fixed_stop", "stop_and_target"} and stop_loss_pct is not None:
            if move_pct <= -abs(float(stop_loss_pct)):
                candidates.append(ticker)
        uses_take_profit_policy = risk_policy in {"take_profit", "stop_and_target"}
        if uses_take_profit_policy and take_profit_pct is not None:
            if move_pct >= abs(float(take_profit_pct)):
                candidates.append(ticker)

    if not candidates:
        return None

    return random.choice(list(dict.fromkeys(candidates)))


def apply_leaps_buy_qty_limits(
    qty: int,
    option_price: float,
    account: AccountPolicyInput,
) -> int:
    max_contracts = account["max_contracts_per_trade"]
    if max_contracts is not None:
        qty = min(qty, int(max_contracts))

    max_premium = account["max_premium_per_trade"]
    if max_premium is not None:
        premium_qty = int(float(max_premium) // option_price)
        qty = min(qty, premium_qty)

    return qty


def build_trade_note(
    learning_enabled: bool,
    forced_sell: str | None,
    risk_policy: str,
    instrument_mode: str,
    account: AccountPolicyInput,
    side: str,
    delta_est: float | None,
    iv_est: float | None,
    strategy_name: str | None,
) -> str:
    note_parts = ["auto-daily"]
    if learning_enabled:
        note_parts.append("selection=heuristic-exploration")
    if forced_sell is not None:
        note_parts.append(f"risk={risk_policy}")
    if instrument_mode == "leaps":
        note_parts.append("mode=leaps")
        note_parts.append(f"strike_offset={account['option_strike_offset_pct']}")
        note_parts.append(f"dte={account['option_min_dte']}-{account['option_max_dte']}")
        note_parts.append(f"type={account['option_type']}")
        if side == "buy" and delta_est is not None:
            note_parts.append(f"delta={delta_est:.2f}")
            if iv_est is not None and iv_est >= 0:
                note_parts.append(f"iv_rank={iv_est:.1f}")

    if strategy_name:
        note_parts.append(f"strategy={strategy_name}")

    return ";".join(note_parts)
