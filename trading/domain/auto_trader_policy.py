from __future__ import annotations

import random
import sqlite3

from trading.models import AccountState


def choose_buy_qty(cash: float, price: float, fee: float) -> int:
    max_qty = int((cash - fee) // price)
    if max_qty < 1:
        return 0
    return random.randint(1, min(5, max_qty))


def choose_sell_qty(position_qty: float) -> int:
    max_qty = int(position_qty)
    if max_qty < 1:
        return 0
    return random.randint(1, min(5, max_qty))


def estimate_delta(abs_strike_offset_pct: float) -> float:
    # Simple monotonic mapping: farther OTM implies lower delta.
    return max(0.05, min(0.95, 0.55 - (abs(abs_strike_offset_pct) / 100.0)))


def estimate_option_premium(
    underlying_price: float,
    delta_est: float,
    min_dte: int | None,
    max_dte: int | None,
) -> float:
    dte_mid = 240.0
    if min_dte is not None and max_dte is not None:
        dte_mid = (float(min_dte) + float(max_dte)) / 2.0
    elif min_dte is not None:
        dte_mid = float(min_dte)
    elif max_dte is not None:
        dte_mid = float(max_dte)

    time_factor = max(0.08, min(0.35, dte_mid / 1000.0))
    delta_factor = 0.4 + delta_est
    premium = underlying_price * time_factor * delta_factor
    return max(0.5, premium)


def option_candidate_allowed(
    account: sqlite3.Row,
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
    account: sqlite3.Row,
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
    account: sqlite3.Row,
    side: str,
    delta_est: float | None,
    iv_est: float | None,
    strategy_name: str | None,
) -> str:
    note_parts = ["auto-daily-learn" if learning_enabled else "auto-daily"]
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
    strategy_name: str | None = None,
) -> str:
    if forced_sell is not None:
        return "sell"

    bias = 0.35
    strategy = (strategy_name or "").strip().lower()
    if "trend" in strategy or "momentum" in strategy or "breakout" in strategy:
        bias = 0.20
    elif "mean" in strategy or "reversion" in strategy or "rsi" in strategy:
        bias = 0.45

    if can_sell and random.random() < bias:
        return "sell"
    return "buy"
