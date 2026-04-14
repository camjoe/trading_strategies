from __future__ import annotations

import random
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

# ---------------------------------------------------------------------------
# Side-selection sell bias by strategy type
# ---------------------------------------------------------------------------

# Default probability of choosing to sell when no strategy context is available
SELL_BIAS_DEFAULT = 0.35

# Lower sell pressure for trend-following / momentum / breakout strategies
# (let winners run)
SELL_BIAS_TREND_MOMENTUM = 0.20

# Higher sell pressure for mean-reversion / RSI strategies
# (take profits closer to the mean)
SELL_BIAS_MEAN_REVERSION = 0.45

# Alternative strategies (external-data driven: news, social, policy) exit
# more aggressively on signal reversal than neutral strategies, but less so
# than pure mean-reversion.
SELL_BIAS_ALTERNATIVE = 0.30

# Maps StrategySpec.strategy_style values to their sell bias probability.
# Extend this when adding new style families.
_STYLE_TO_SELL_BIAS: dict[str, float] = {
    "trend": SELL_BIAS_TREND_MOMENTUM,
    "mean_reversion": SELL_BIAS_MEAN_REVERSION,
    "alternative": SELL_BIAS_ALTERNATIVE,
}


class AccountConfig(Protocol):
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
    account: AccountConfig,
    ticker: str,
    price: float,
    iv_rank_proxy: dict[str, float],
    *,
    estimate_delta_fn,
) -> tuple[bool, float, float]:
    strike_offset = float(account["option_strike_offset_pct"] or 0.0)
    delta_est = estimate_delta_fn(strike_offset)
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
        if risk_policy in {"take_profit", "stop_and_target"} and take_profit_pct is not None:
            if move_pct >= abs(float(take_profit_pct)):
                candidates.append(ticker)

    if not candidates:
        return None

    return random.choice(list(dict.fromkeys(candidates)))


def choose_buy_ticker(
    universe: list[str],
    prices: dict[str, float],
    state: AccountState,
    learning_enabled: bool,
) -> str:
    if not learning_enabled:
        return random.choice(universe)

    scored: list[tuple[float, str]] = []
    for ticker in universe:
        price = prices.get(ticker)
        if price is None or price <= 0:
            continue
        avg_cost = state.avg_cost.get(ticker, 0.0)
        if avg_cost > 0:
            score = (price / avg_cost) - 1.0
        else:
            score = 0.0
        scored.append((score, ticker))

    if not scored:
        return random.choice(universe)

    scored.sort(key=lambda x: x[0], reverse=True)
    top_n = max(1, len(scored) // 2)
    return random.choice([ticker for _score, ticker in scored[:top_n]])


def choose_sell_ticker(
    can_sell: list[str],
    prices: dict[str, float],
    state: AccountState,
    learning_enabled: bool,
) -> str:
    if not learning_enabled:
        return random.choice(can_sell)

    scored: list[tuple[float, str]] = []
    for ticker in can_sell:
        price = prices.get(ticker)
        avg_cost = state.avg_cost.get(ticker, 0.0)
        if price is None or price <= 0 or avg_cost <= 0:
            score = 0.0
        else:
            score = (price / avg_cost) - 1.0
        scored.append((score, ticker))

    scored.sort(key=lambda x: x[0])
    worst_n = max(1, len(scored) // 2)
    return random.choice([ticker for _score, ticker in scored[:worst_n]])


def apply_leaps_buy_qty_limits(
    qty: int,
    option_price: float,
    account: AccountConfig,
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
    account: AccountConfig,
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


def choose_side(
    forced_sell: str | None,
    can_sell: list[str],
    strategy_style: str | None = None,
) -> str:
    if forced_sell is not None:
        return "sell"

    bias = _STYLE_TO_SELL_BIAS.get(strategy_style or "", SELL_BIAS_DEFAULT)

    if can_sell and random.random() < bias:
        return "sell"
    return "buy"
