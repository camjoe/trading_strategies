"""LEAPS/option heuristics: delta and premium estimates, eligibility, and contract limits.

Simplified, dependency-free approximations — enough for the auto-trader to size and
screen option candidates without a pricing library.
"""

from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Delta estimation (monotonic strike-offset -> delta mapping)
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
