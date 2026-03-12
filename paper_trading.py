import argparse
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yfinance as yf

DB_PATH = Path("paper_trading") / "paper_trading.db"


@dataclass
class AccountState:
    cash: float
    positions: dict[str, float]
    avg_cost: dict[str, float]
    realized_pnl: float


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def ensure_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            strategy TEXT NOT NULL,
            initial_cash REAL NOT NULL,
            created_at TEXT NOT NULL,
            benchmark_ticker TEXT NOT NULL DEFAULT 'SPY'
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
            qty REAL NOT NULL,
            price REAL NOT NULL,
            fee REAL NOT NULL DEFAULT 0,
            trade_time TEXT NOT NULL,
            note TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        );

        CREATE TABLE IF NOT EXISTS equity_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            snapshot_time TEXT NOT NULL,
            cash REAL NOT NULL,
            market_value REAL NOT NULL,
            equity REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            unrealized_pnl REAL NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        );
        """
    )
    ensure_accounts_benchmark_column(conn)
    conn.commit()


def ensure_accounts_benchmark_column(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(accounts)").fetchall()
    names = {str(c[1]) for c in cols}
    if "benchmark_ticker" not in names:
        conn.execute(
            "ALTER TABLE accounts ADD COLUMN benchmark_ticker TEXT NOT NULL DEFAULT 'SPY'"
        )
        conn.commit()


def get_account(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise ValueError(f"Account '{name}' not found.")
    return row


def create_account(
    conn: sqlite3.Connection,
    name: str,
    strategy: str,
    initial_cash: float,
    benchmark_ticker: str,
) -> None:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be greater than 0.")
    conn.execute(
        """
        INSERT INTO accounts (name, strategy, initial_cash, created_at, benchmark_ticker)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, strategy, float(initial_cash), utc_now_iso(), benchmark_ticker.upper().strip()),
    )
    conn.commit()


def set_benchmark(conn: sqlite3.Connection, account_name: str, benchmark_ticker: str) -> None:
    account = get_account(conn, account_name)
    conn.execute(
        "UPDATE accounts SET benchmark_ticker = ? WHERE id = ?",
        (benchmark_ticker.upper().strip(), account["id"]),
    )
    conn.commit()


def list_accounts(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, name, strategy, initial_cash, created_at, benchmark_ticker
        FROM accounts
        ORDER BY id
        """
    ).fetchall()
    if not rows:
        print("No paper accounts found.")
        return

    for row in rows:
        print(
            f"[{row['id']}] {row['name']} | strategy={row['strategy']} | "
            f"initial_cash={row['initial_cash']:.2f} | benchmark={row['benchmark_ticker']} | "
            f"created={row['created_at']}"
        )


def load_trades(conn: sqlite3.Connection, account_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT ticker, side, qty, price, fee, trade_time
        FROM trades
        WHERE account_id = ?
        ORDER BY trade_time, id
        """,
        (account_id,),
    ).fetchall()


def compute_account_state(initial_cash: float, trades: list[sqlite3.Row]) -> AccountState:
    positions: dict[str, float] = defaultdict(float)
    avg_cost: dict[str, float] = defaultdict(float)
    cash = float(initial_cash)
    realized = 0.0

    for t in trades:
        ticker = str(t["ticker"]).upper()
        side = str(t["side"]).lower()
        qty = float(t["qty"])
        price = float(t["price"])
        fee = float(t["fee"])

        if qty <= 0:
            raise ValueError("Trade quantity must be > 0.")
        if price <= 0:
            raise ValueError("Trade price must be > 0.")

        if side == "buy":
            old_qty = positions[ticker]
            new_qty = old_qty + qty
            old_value = old_qty * avg_cost[ticker]
            trade_value = qty * price + fee
            avg_cost[ticker] = (old_value + trade_value) / new_qty
            positions[ticker] = new_qty
            cash -= trade_value

        elif side == "sell":
            old_qty = positions[ticker]
            if qty > old_qty:
                raise ValueError(
                    f"Invalid sell for {ticker}: trying to sell {qty}, holding {old_qty}."
                )

            proceeds = qty * price - fee
            cash += proceeds
            realized += (price - avg_cost[ticker]) * qty - fee
            positions[ticker] = old_qty - qty

            if positions[ticker] == 0:
                avg_cost[ticker] = 0.0
        else:
            raise ValueError(f"Unsupported side: {side}")

    positions = {k: v for k, v in positions.items() if v > 0}
    avg_cost = {k: avg_cost[k] for k in positions}

    return AccountState(cash=cash, positions=positions, avg_cost=avg_cost, realized_pnl=realized)


def record_trade(
    conn: sqlite3.Connection,
    account_name: str,
    side: str,
    ticker: str,
    qty: float,
    price: float,
    fee: float,
    trade_time: str | None,
    note: str | None,
) -> None:
    account = get_account(conn, account_name)
    side = side.lower().strip()
    ticker = ticker.upper().strip()

    if side not in {"buy", "sell"}:
        raise ValueError("side must be one of: buy, sell")

    existing_state = compute_account_state(account["initial_cash"], load_trades(conn, account["id"]))
    if side == "buy":
        required_cash = qty * price + fee
        if required_cash > existing_state.cash:
            raise ValueError(
                f"Insufficient cash: need {required_cash:.2f}, available {existing_state.cash:.2f}."
            )

    conn.execute(
        """
        INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account["id"],
            ticker,
            side,
            float(qty),
            float(price),
            float(fee),
            trade_time or utc_now_iso(),
            note,
        ),
    )
    conn.commit()


def fetch_latest_prices(tickers: list[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="5d", auto_adjust=True)
            if hist.empty:
                continue
            close = hist["Close"].dropna()
            if close.empty:
                continue
            prices[ticker] = float(close.iloc[-1])
        except Exception:
            # Keep report resilient if one ticker lookup fails.
            continue
    return prices


def build_account_stats(conn: sqlite3.Connection, account: sqlite3.Row) -> tuple[AccountState, dict[str, float], float, float, float]:
    trades = load_trades(conn, account["id"])
    state = compute_account_state(account["initial_cash"], trades)
    tickers = sorted(state.positions.keys())
    prices = fetch_latest_prices(tickers) if tickers else {}

    market_value = 0.0
    unrealized = 0.0
    for ticker, qty in state.positions.items():
        price = prices.get(ticker)
        if price is None:
            continue
        market_value += qty * price
        unrealized += (price - state.avg_cost[ticker]) * qty

    equity = state.cash + market_value
    return state, prices, market_value, unrealized, equity


def benchmark_stats(benchmark_ticker: str, initial_cash: float, created_at: str) -> tuple[float | None, float | None]:
    ticker = benchmark_ticker.upper().strip()
    start_date = created_at[:10]
    try:
        hist = yf.Ticker(ticker).history(start=start_date, period="max", auto_adjust=True)
        if hist.empty:
            return None, None

        close = hist["Close"].dropna()
        if close.empty:
            return None, None

        start_price = float(close.iloc[0])
        end_price = float(close.iloc[-1])
        bench_equity = initial_cash * (end_price / start_price)
        bench_return_pct = ((bench_equity / initial_cash) - 1.0) * 100.0
        return bench_equity, bench_return_pct
    except Exception:
        return None, None


def infer_overall_trend(
    conn: sqlite3.Connection,
    account_id: int,
    current_equity: float,
    lookback: int,
) -> str:
    rows = conn.execute(
        """
        SELECT equity
        FROM equity_snapshots
        WHERE account_id = ?
        ORDER BY snapshot_time DESC, id DESC
        LIMIT ?
        """,
        (account_id, int(max(lookback, 2))),
    ).fetchall()

    history = [float(r["equity"]) for r in rows]
    history.reverse()
    history.append(current_equity)

    if len(history) < 3:
        return "insufficient-data"

    first = history[0]
    last = history[-1]
    if first == 0:
        return "insufficient-data"

    move_pct = ((last - first) / first) * 100.0
    if move_pct > 1.0:
        return "up"
    if move_pct < -1.0:
        return "down"
    return "flat"


def account_report(conn: sqlite3.Connection, account_name: str) -> tuple[dict[str, float], dict[str, float]]:
    account = get_account(conn, account_name)
    state, prices, market_value, unrealized, equity = build_account_stats(conn, account)
    benchmark_equity, benchmark_return_pct = benchmark_stats(
        account["benchmark_ticker"], account["initial_cash"], account["created_at"]
    )
    strategy_return_pct = ((equity / account["initial_cash"]) - 1.0) * 100.0

    print(f"Account: {account['name']} | Strategy: {account['strategy']}")
    print(f"Benchmark: {account['benchmark_ticker']}")
    print(f"Initial Cash: {account['initial_cash']:.2f}")
    print(f"Cash: {state.cash:.2f}")
    print(f"Market Value: {market_value:.2f}")
    print(f"Equity: {equity:.2f}")
    print(f"Strategy Return %: {strategy_return_pct:.2f}")
    print(f"Realized PnL: {state.realized_pnl:.2f}")
    print(f"Unrealized PnL: {unrealized:.2f}")
    if benchmark_equity is not None and benchmark_return_pct is not None:
        alpha_pct = strategy_return_pct - benchmark_return_pct
        print(f"Benchmark Equity: {benchmark_equity:.2f}")
        print(f"Benchmark Return %: {benchmark_return_pct:.2f}")
        print(f"Strategy Alpha vs Benchmark %: {alpha_pct:.2f}")
    else:
        print("Benchmark comparison: unavailable (price history not found)")

    if not state.positions:
        print("Open Positions: none")
    else:
        print("Open Positions:")
        for ticker in sorted(state.positions.keys()):
            qty = state.positions[ticker]
            avg = state.avg_cost[ticker]
            px = prices.get(ticker)
            px_display = f"{px:.2f}" if px is not None else "N/A"
            print(f"- {ticker}: qty={qty:.4f}, avg_cost={avg:.2f}, last_price={px_display}")

    stats = {
        "cash": state.cash,
        "market_value": market_value,
        "equity": equity,
        "realized_pnl": state.realized_pnl,
        "unrealized_pnl": unrealized,
        "strategy_return_pct": strategy_return_pct,
    }
    return stats, state.positions


def compare_strategies(conn: sqlite3.Connection, lookback: int) -> None:
    accounts = conn.execute(
        """
        SELECT id, name, strategy, initial_cash, created_at, benchmark_ticker
        FROM accounts
        ORDER BY strategy, name
        """
    ).fetchall()

    if not accounts:
        print("No paper accounts found.")
        return

    print("Per-strategy comparison:")
    for account in accounts:
        state, _prices, market_value, _unrealized, equity = build_account_stats(conn, account)
        strategy_return_pct = ((equity / account["initial_cash"]) - 1.0) * 100.0
        bench_equity, bench_return_pct = benchmark_stats(
            account["benchmark_ticker"], account["initial_cash"], account["created_at"]
        )
        trend = infer_overall_trend(conn, account["id"], equity, lookback)

        position_count = len(state.positions)
        if state.positions:
            # Keep summary compact but useful.
            sorted_positions = sorted(state.positions.items(), key=lambda x: x[0])
            positions_text = ", ".join([f"{k}:{v:.2f}" for k, v in sorted_positions[:5]])
            if len(sorted_positions) > 5:
                positions_text += ", ..."
        else:
            positions_text = "none"

        print(
            f"- {account['name']} | strategy={account['strategy']} | benchmark={account['benchmark_ticker']}"
        )
        print(
            f"  equity={equity:.2f} return={strategy_return_pct:.2f}% "
            f"positions={position_count} trend={trend}"
        )
        if bench_equity is not None and bench_return_pct is not None:
            alpha_pct = strategy_return_pct - bench_return_pct
            print(
                f"  benchmark_equity={bench_equity:.2f} benchmark_return={bench_return_pct:.2f}% "
                f"alpha={alpha_pct:.2f}%"
            )
        else:
            print("  benchmark_equity=N/A benchmark_return=N/A alpha=N/A")
        print(f"  positions: {positions_text}")


def snapshot_account(conn: sqlite3.Connection, account_name: str, snapshot_time: str | None) -> None:
    account = get_account(conn, account_name)
    stats, _ = account_report(conn, account_name)
    conn.execute(
        """
        INSERT INTO equity_snapshots (
            account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account["id"],
            snapshot_time or utc_now_iso(),
            stats["cash"],
            stats["market_value"],
            stats["equity"],
            stats["realized_pnl"],
            stats["unrealized_pnl"],
        ),
    )
    conn.commit()
    print("Snapshot saved.")


def show_snapshots(conn: sqlite3.Connection, account_name: str, limit: int) -> None:
    account = get_account(conn, account_name)
    rows = conn.execute(
        """
        SELECT snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        FROM equity_snapshots
        WHERE account_id = ?
        ORDER BY snapshot_time DESC, id DESC
        LIMIT ?
        """,
        (account["id"], int(limit)),
    ).fetchall()

    if not rows:
        print("No snapshots found.")
        return

    print(f"Snapshot history (latest {limit}) for {account_name}:")
    for r in rows:
        print(
            f"- {r['snapshot_time']} | equity={r['equity']:.2f} cash={r['cash']:.2f} "
            f"mv={r['market_value']:.2f} realized={r['realized_pnl']:.2f} "
            f"unrealized={r['unrealized_pnl']:.2f}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Paper trading accounts per strategy with trade and equity tracking."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize paper trading database.")
    sub.add_parser("list-accounts", help="List all paper trading accounts.")

    p_create = sub.add_parser("create-account", help="Create a new paper account.")
    p_create.add_argument("--name", required=True, help="Account name, e.g. trend_v1")
    p_create.add_argument("--strategy", required=True, help="Strategy label")
    p_create.add_argument("--initial-cash", type=float, required=True, help="Starting cash")
    p_create.add_argument(
        "--benchmark",
        default="SPY",
        help="Benchmark ticker for this strategy account (default: SPY)",
    )

    p_set_benchmark = sub.add_parser("set-benchmark", help="Set benchmark ticker for an account.")
    p_set_benchmark.add_argument("--account", required=True, help="Account name")
    p_set_benchmark.add_argument("--benchmark", required=True, help="Benchmark ticker, e.g. SPY")

    p_trade = sub.add_parser("trade", help="Record a mock buy or sell.")
    p_trade.add_argument("--account", required=True, help="Account name")
    p_trade.add_argument("--side", required=True, choices=["buy", "sell"], help="Order side")
    p_trade.add_argument("--ticker", required=True, help="Ticker symbol")
    p_trade.add_argument("--qty", type=float, required=True, help="Trade quantity")
    p_trade.add_argument("--price", type=float, required=True, help="Execution price")
    p_trade.add_argument("--fee", type=float, default=0.0, help="Optional trading fee")
    p_trade.add_argument("--time", default=None, help="Optional trade time (ISO string)")
    p_trade.add_argument("--note", default=None, help="Optional trade note")

    p_report = sub.add_parser("report", help="Show account status and open positions.")
    p_report.add_argument("--account", required=True, help="Account name")

    p_snapshot = sub.add_parser("snapshot", help="Save equity snapshot for an account.")
    p_snapshot.add_argument("--account", required=True, help="Account name")
    p_snapshot.add_argument("--time", default=None, help="Optional snapshot time (ISO string)")

    p_history = sub.add_parser("snapshot-history", help="Show account snapshot history.")
    p_history.add_argument("--account", required=True, help="Account name")
    p_history.add_argument("--limit", type=int, default=20, help="Number of rows to show")

    p_compare = sub.add_parser(
        "compare-strategies",
        help="Compare accounts by strategy label, positions, benchmark, and trend.",
    )
    p_compare.add_argument(
        "--lookback",
        type=int,
        default=10,
        help="Snapshot lookback count for trend classification (default: 10)",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    conn = ensure_db()
    try:
        if args.command == "init":
            print(f"Initialized: {DB_PATH}")

        elif args.command == "create-account":
            create_account(conn, args.name, args.strategy, args.initial_cash, args.benchmark)
            print(
                f"Created account '{args.name}' for strategy '{args.strategy}' "
                f"with benchmark '{args.benchmark.upper()}'."
            )

        elif args.command == "set-benchmark":
            set_benchmark(conn, args.account, args.benchmark)
            print(f"Updated benchmark for '{args.account}' to '{args.benchmark.upper()}'.")

        elif args.command == "list-accounts":
            list_accounts(conn)

        elif args.command == "trade":
            record_trade(
                conn,
                account_name=args.account,
                side=args.side,
                ticker=args.ticker,
                qty=args.qty,
                price=args.price,
                fee=args.fee,
                trade_time=args.time,
                note=args.note,
            )
            print("Trade recorded.")

        elif args.command == "report":
            account_report(conn, args.account)

        elif args.command == "snapshot":
            snapshot_account(conn, args.account, args.time)

        elif args.command == "snapshot-history":
            show_snapshots(conn, args.account, args.limit)

        elif args.command == "compare-strategies":
            compare_strategies(conn, args.lookback)

        else:
            parser.error(f"Unsupported command: {args.command}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
