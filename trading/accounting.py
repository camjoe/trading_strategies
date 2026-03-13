import sqlite3
from collections import defaultdict

try:
    from trading.accounts import get_account, utc_now_iso
    from trading.models import AccountState
except ModuleNotFoundError:
    from accounts import get_account, utc_now_iso
    from models import AccountState


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
