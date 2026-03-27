import argparse
import random
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypeAlias

from common.market_data import get_provider
from common.tickers import load_tickers_from_file
from common.time import utc_now_iso

from trading.accounting import compute_account_state, load_trades, record_trade
from trading.accounts import get_account
from trading.database.db_coercion import coerce_float
from trading.database.db import ensure_db
from trading.models import AccountState
from trading.pricing import fetch_latest_prices
from trading.rotation import (
    is_rotation_due,
    next_rotation_state,
    parse_rotation_schedule,
    resolve_active_strategy,
    resolve_optimality_mode,
    resolve_rotation_mode,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute 1-5 simulated daily paper trades per account."
    )
    parser.add_argument(
        "--accounts",
        required=True,
        help="Comma-separated account names, e.g. momentum_5k,meanrev_5k",
    )
    parser.add_argument(
        "--tickers-file",
        default="trading/trade_universe.txt",
        help="Path to ticker universe file (default: trading/trade_universe.txt)",
    )
    parser.add_argument("--min-trades", type=int, default=1, help="Minimum trades per account")
    parser.add_argument("--max-trades", type=int, default=5, help="Maximum trades per account")
    parser.add_argument("--fee", type=float, default=0.0, help="Per-trade fee")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed")
    return parser.parse_args()


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


def build_iv_rank_proxy(universe: list[str]) -> dict[str, float]:
    # IV rank proxy: percentile rank of 1y realized volatility inside the current trade universe.
    vols: dict[str, float] = {}
    for ticker in universe:
        try:
            close = get_provider().fetch_close_series(ticker, "1y")
            if close is None or len(close) < 30:
                continue
            daily_ret = close.pct_change().dropna()
            if daily_ret.empty:
                continue
            vol_annual = float(daily_ret.std() * (252 ** 0.5))
            vols[ticker] = vol_annual
        except Exception:
            continue

    if not vols:
        return {}

    sorted_items = sorted(vols.items(), key=lambda x: x[1])
    n = len(sorted_items)
    if n == 1:
        return {sorted_items[0][0]: 50.0}

    out: dict[str, float] = {}
    for i, (ticker, _vol) in enumerate(sorted_items):
        out[ticker] = (i / (n - 1)) * 100.0
    return out


def estimate_delta(abs_strike_offset_pct: float) -> float:
    # Simple monotonic mapping: farther OTM implies lower delta.
    return max(0.05, min(0.95, 0.55 - (abs(abs_strike_offset_pct) / 100.0)))


def estimate_option_premium(underlying_price: float, delta_est: float, min_dte: int | None, max_dte: int | None) -> float:
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
        if risk_policy in {"take_profit", "stop_and_target"} and take_profit_pct is not None:
            if move_pct >= abs(float(take_profit_pct)):
                candidates.append(ticker)

    if not candidates:
        return None

    return random.choice(list(dict.fromkeys(candidates)))


def choose_buy_ticker(universe: list[str], prices: dict[str, float], state: AccountState, learning_enabled: bool) -> str:
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
    return random.choice([t for _score, t in scored[:top_n]])


def choose_sell_ticker(can_sell: list[str], prices: dict[str, float], state: AccountState, learning_enabled: bool) -> str:
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
    return random.choice([t for _score, t in scored[:worst_n]])


BuyTradeSelection: TypeAlias = tuple[str, int, float, float | None, float | None]
SellTradeSelection: TypeAlias = tuple[str, int, float]


def _build_leaps_candidates(
    account: sqlite3.Row,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
) -> list[tuple[str, float, float]]:
    candidates: list[tuple[str, float, float]] = []
    for ticker in universe:
        price = prices.get(ticker)
        if price is None or price <= 0:
            continue

        ok, delta_est, iv_est = option_candidate_allowed(
            account,
            ticker,
            float(price),
            iv_rank_proxy,
        )
        if ok:
            candidates.append((ticker, delta_est, iv_est))

    return candidates


def _apply_leaps_buy_qty_limits(
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


def _build_trade_note(
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


def _choose_side(forced_sell: str | None, can_sell: list[str], strategy_name: str | None = None) -> str:
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


def _rotate_account_if_due(
    conn: sqlite3.Connection,
    account_name: str,
    account: sqlite3.Row,
    now_iso: str,
) -> sqlite3.Row:
    if not is_rotation_due(account, as_of_iso=now_iso):
        return account

    rotation_mode = resolve_rotation_mode(account)
    if rotation_mode == "optimal":
        optimal = _select_optimal_strategy(conn, account, now_iso)
        active = optimal or resolve_active_strategy(account)
        schedule = parse_rotation_schedule(account["rotation_schedule"])
        if schedule and active in schedule:
            active_idx = schedule.index(active)
        else:
            active_idx = int(account["rotation_active_index"] or 0)
        next_state = {
            "rotation_active_index": active_idx,
            "rotation_active_strategy": active,
            "rotation_last_at": now_iso,
        }
    else:
        next_state = next_rotation_state(account, as_of_iso=now_iso)

    conn.execute(
        """
        UPDATE accounts
        SET strategy = ?,
            rotation_active_index = ?,
            rotation_active_strategy = ?,
            rotation_last_at = ?
        WHERE id = ?
        """,
        (
            next_state["rotation_active_strategy"],
            int(next_state["rotation_active_index"]),
            next_state["rotation_active_strategy"],
            next_state["rotation_last_at"],
            account["id"],
        ),
    )
    conn.commit()
    return get_account(conn, account_name)


def _parse_as_of_iso(as_of_iso: str) -> datetime:
    text = as_of_iso.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _safe_return_pct(starting_equity: object, ending_equity: object) -> float | None:
    start = coerce_float(starting_equity)
    end = coerce_float(ending_equity)
    if start is None or end is None:
        return None
    if start <= 0:
        return None
    return ((end / start) - 1.0) * 100.0


def _select_optimal_strategy(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    as_of_iso: str,
) -> str | None:
    schedule = parse_rotation_schedule(account["rotation_schedule"])
    if not schedule:
        return None

    lookback_days = int(account["rotation_lookback_days"] or 180)
    as_of_dt = _parse_as_of_iso(as_of_iso)
    end_day = as_of_dt.date().isoformat()
    start_day = (as_of_dt - timedelta(days=lookback_days)).date().isoformat()

    placeholders = ",".join(["?"] * len(schedule))
    rows = conn.execute(
        f"""
        SELECT
            r.strategy_name,
            r.end_date,
            (
                SELECT s.equity
                FROM backtest_equity_snapshots s
                WHERE s.run_id = r.id
                ORDER BY s.snapshot_time ASC, s.id ASC
                LIMIT 1
            ) AS starting_equity,
            (
                SELECT s.equity
                FROM backtest_equity_snapshots s
                WHERE s.run_id = r.id
                ORDER BY s.snapshot_time DESC, s.id DESC
                LIMIT 1
            ) AS ending_equity
        FROM backtest_runs r
        WHERE r.account_id = ?
          AND r.strategy_name IN ({placeholders})
          AND r.end_date >= ?
          AND r.end_date <= ?
        ORDER BY r.end_date DESC, r.id DESC
        """,
        (account["id"], *schedule, start_day, end_day),
    ).fetchall()

    if not rows:
        return None

    by_strategy: dict[str, list[float]] = {}
    latest_by_strategy: dict[str, float] = {}
    for row in rows:
        strategy_name = str(row["strategy_name"] or "").strip()
        if not strategy_name:
            continue
        ret = _safe_return_pct(row["starting_equity"], row["ending_equity"])
        if ret is None:
            continue
        by_strategy.setdefault(strategy_name, []).append(ret)
        if strategy_name not in latest_by_strategy:
            latest_by_strategy[strategy_name] = ret

    if not by_strategy:
        return None

    optimality_mode = resolve_optimality_mode(account)
    scores: dict[str, float] = {}
    if optimality_mode == "average_return":
        for strategy_name, values in by_strategy.items():
            scores[strategy_name] = sum(values) / len(values)
    else:
        scores = dict(latest_by_strategy)

    if not scores:
        return None

    best_strategy = max(scores.items(), key=lambda item: item[1])[0]
    return best_strategy if best_strategy in schedule else None


def _prepare_buy_trade(
    account: sqlite3.Row,
    instrument_mode: str,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    state: AccountState,
    learning_enabled: bool,
    fee: float,
) -> BuyTradeSelection | None:
    if instrument_mode == "leaps":
        candidates = _build_leaps_candidates(account, universe, prices, iv_rank_proxy)
        if not candidates:
            return None

        ticker, delta_est, iv_est = random.choice(candidates)
        price = prices.get(ticker)
        if price is None or price <= 0:
            return None

        option_price = estimate_option_premium(
            float(price),
            delta_est,
            int(account["option_min_dte"]) if account["option_min_dte"] is not None else None,
            int(account["option_max_dte"]) if account["option_max_dte"] is not None else None,
        )
        qty = choose_buy_qty(state.cash, option_price, fee)
        if qty <= 0:
            return None

        qty = _apply_leaps_buy_qty_limits(qty, option_price, account)
        if qty <= 0:
            return None

        return ticker, qty, float(option_price), delta_est, iv_est

    ticker = choose_buy_ticker(universe, prices, state, learning_enabled)
    price = prices.get(ticker)
    if price is None or price <= 0:
        return None

    qty = choose_buy_qty(state.cash, float(price), fee)
    if qty <= 0:
        return None

    return ticker, qty, float(price), None, None


def _prepare_sell_trade(
    can_sell: list[str],
    forced_sell: str | None,
    prices: dict[str, float],
    state: AccountState,
    learning_enabled: bool,
    instrument_mode: str,
) -> SellTradeSelection | None:
    if forced_sell is not None:
        ticker = forced_sell
    else:
        ticker = choose_sell_ticker(can_sell, prices, state, learning_enabled)

    price = prices.get(ticker)
    if price is None or price <= 0:
        return None

    qty = choose_sell_qty(state.positions[ticker])
    if qty <= 0:
        return None

    if instrument_mode == "leaps":
        qty = min(qty, 2)

    return ticker, qty, float(price)


def run_for_account(
    conn: sqlite3.Connection,
    account_name: str,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    min_trades: int,
    max_trades: int,
    fee: float,
) -> int:
    account = get_account(conn, account_name)
    now_iso = utc_now_iso()
    account = _rotate_account_if_due(conn, account_name, account, now_iso)
    active_strategy = resolve_active_strategy(account)
    learning_enabled = bool(int(account["learning_enabled"]))
    risk_policy = str(account["risk_policy"]).strip().lower()
    stop_loss_pct = account["stop_loss_pct"]
    take_profit_pct = account["take_profit_pct"]
    instrument_mode = str(account["instrument_mode"]).strip().lower()
    target = random.randint(min_trades, max_trades)
    executed = 0
    for _ in range(target):
        state = compute_account_state(account["initial_cash"], load_trades(conn, account["id"]))
        can_sell = [t for t, q in state.positions.items() if q >= 1]

        forced_sell = choose_sell_ticker_by_risk(
            can_sell,
            prices,
            state,
            risk_policy,
            stop_loss_pct,
            take_profit_pct,
        )

        side = _choose_side(forced_sell, can_sell, active_strategy)

        delta_est: float | None = None
        iv_est: float | None = None

        if side == "buy":
            prepared_buy = _prepare_buy_trade(
                account,
                instrument_mode,
                universe,
                prices,
                iv_rank_proxy,
                state,
                learning_enabled,
                fee,
            )
            if prepared_buy is None:
                continue

            ticker, qty, trade_price, delta_est, iv_est = prepared_buy
        else:
            prepared_sell = _prepare_sell_trade(
                can_sell,
                forced_sell,
                prices,
                state,
                learning_enabled,
                instrument_mode,
            )
            if prepared_sell is None:
                continue

            ticker, qty, trade_price = prepared_sell

        record_trade(
            conn,
            account_name=account_name,
            side=side,
            ticker=ticker,
            qty=qty,
            price=trade_price,
            fee=fee,
            trade_time=utc_now_iso(),
            note=_build_trade_note(
                learning_enabled,
                forced_sell,
                risk_policy,
                instrument_mode,
                account,
                side,
                delta_est,
                iv_est,
                active_strategy,
            ),
        )
        executed += 1

    return executed


def main() -> None:
    args = parse_args()
    if args.min_trades < 1:
        raise ValueError("--min-trades must be >= 1")
    if args.max_trades < args.min_trades:
        raise ValueError("--max-trades must be >= --min-trades")

    if args.seed is not None:
        random.seed(args.seed)

    accounts = [a.strip() for a in args.accounts.split(",") if a.strip()]
    if not accounts:
        raise ValueError("No accounts provided.")

    universe = load_tickers_from_file(args.tickers_file)
    if not universe:
        raise ValueError("Ticker universe is empty.")

    prices = fetch_latest_prices(universe)
    if not prices:
        raise ValueError("Could not fetch any prices for ticker universe.")
    iv_rank_proxy = build_iv_rank_proxy(universe)

    conn = ensure_db()
    try:
        for account_name in accounts:
            executed = run_for_account(
                conn=conn,
                account_name=account_name,
                universe=universe,
                prices=prices,
                iv_rank_proxy=iv_rank_proxy,
                min_trades=args.min_trades,
                max_trades=args.max_trades,
                fee=args.fee,
            )
            print(f"{account_name}: executed {executed} trades")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
