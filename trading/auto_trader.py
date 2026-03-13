import argparse
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from trading.accounting import compute_account_state, load_trades, record_trade
    from trading.accounts import get_account
    from trading.db import ensure_db
    from trading.pricing import fetch_latest_prices
except ModuleNotFoundError:
    from accounting import compute_account_state, load_trades, record_trade
    from accounts import get_account
    from db import ensure_db
    from pricing import fetch_latest_prices


def load_tickers_from_file(file_path: str) -> list[str]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Ticker file not found: {file_path}")

    tickers: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = line.replace(",", " ").split()
        tickers.extend([t.strip().upper() for t in tokens if t.strip()])

    return list(dict.fromkeys(tickers))


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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def choose_buy_ticker(universe: list[str], prices: dict[str, float], state: object, learning_enabled: bool) -> str:
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


def choose_sell_ticker(can_sell: list[str], prices: dict[str, float], state: object, learning_enabled: bool) -> str:
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


def run_for_account(
    conn: sqlite3.Connection,
    account_name: str,
    universe: list[str],
    prices: dict[str, float],
    min_trades: int,
    max_trades: int,
    fee: float,
) -> int:
    account = get_account(conn, account_name)
    learning_enabled = bool(int(account["learning_enabled"]))
    target = random.randint(min_trades, max_trades)
    executed = 0

    for _ in range(target):
        state = compute_account_state(account["initial_cash"], load_trades(conn, account["id"]))
        can_sell = [t for t, q in state.positions.items() if q >= 1]

        side = "buy"
        if can_sell and random.random() < 0.35:
            side = "sell"

        if side == "buy":
            ticker = choose_buy_ticker(universe, prices, state, learning_enabled)
            price = prices.get(ticker)
            if price is None or price <= 0:
                continue
            qty = choose_buy_qty(state.cash, price, fee)
            if qty <= 0:
                continue
        else:
            ticker = choose_sell_ticker(can_sell, prices, state, learning_enabled)
            price = prices.get(ticker)
            if price is None or price <= 0:
                continue
            qty = choose_sell_qty(state.positions[ticker])
            if qty <= 0:
                continue

        record_trade(
            conn,
            account_name=account_name,
            side=side,
            ticker=ticker,
            qty=qty,
            price=float(price),
            fee=fee,
            trade_time=utc_now_iso(),
            note="auto-daily-learn" if learning_enabled else "auto-daily",
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

    conn = ensure_db()
    try:
        for account_name in accounts:
            executed = run_for_account(
                conn=conn,
                account_name=account_name,
                universe=universe,
                prices=prices,
                min_trades=args.min_trades,
                max_trades=args.max_trades,
                fee=args.fee,
            )
            print(f"{account_name}: executed {executed} trades")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
