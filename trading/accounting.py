import sqlite3
from collections import defaultdict
from trading.accounts import get_account, utc_now_iso
from trading.models import AccountState


VALID_SIDES = {"buy", "sell"}


def _normalize_trade_fields(trade: sqlite3.Row) -> tuple[str, str, float, float, float]:
    return (
        str(trade["ticker"]).upper(),
        str(trade["side"]).lower(),
        float(trade["qty"]),
        float(trade["price"]),
        float(trade["fee"]),
    )


def _validate_trade_values(qty: float, price: float) -> None:
    if qty <= 0:
        raise ValueError("Trade quantity must be > 0.")
    if price <= 0:
        raise ValueError("Trade price must be > 0.")


def _apply_buy(
    ticker: str,
    qty: float,
    price: float,
    fee: float,
    positions: dict[str, float],
    avg_cost: dict[str, float],
    cash: float,
) -> float:
    old_qty = positions[ticker]
    new_qty = old_qty + qty
    old_value = old_qty * avg_cost[ticker]
    trade_value = qty * price + fee

    avg_cost[ticker] = (old_value + trade_value) / new_qty
    positions[ticker] = new_qty
    return cash - trade_value


def _apply_sell(
    ticker: str,
    qty: float,
    price: float,
    fee: float,
    positions: dict[str, float],
    avg_cost: dict[str, float],
    cash: float,
    realized: float,
) -> tuple[float, float]:
    old_qty = positions[ticker]
    if qty > old_qty:
        raise ValueError(f"Invalid sell for {ticker}: trying to sell {qty}, holding {old_qty}.")

    proceeds = qty * price - fee
    cash += proceeds
    realized += (price - avg_cost[ticker]) * qty - fee
    positions[ticker] = old_qty - qty

    if positions[ticker] == 0:
        avg_cost[ticker] = 0.0

    return cash, realized


def _compact_positions(
    positions: dict[str, float], avg_cost: dict[str, float]
) -> tuple[dict[str, float], dict[str, float]]:
    open_positions = {ticker: qty for ticker, qty in positions.items() if qty > 0}
    open_avg_cost = {ticker: avg_cost[ticker] for ticker in open_positions}
    return open_positions, open_avg_cost


def _normalize_order_input(side: str, ticker: str) -> tuple[str, str]:
    normalized_side = side.lower().strip()
    normalized_ticker = ticker.upper().strip()

    if normalized_side not in VALID_SIDES:
        raise ValueError("side must be one of: buy, sell")

    return normalized_side, normalized_ticker


def _ensure_sufficient_cash_for_buy(
    side: str,
    qty: float,
    price: float,
    fee: float,
    available_cash: float,
) -> None:
    if side != "buy":
        return

    required_cash = qty * price + fee
    if required_cash > available_cash:
        raise ValueError(f"Insufficient cash: need {required_cash:.2f}, available {available_cash:.2f}.")


def _account_state_from_db(conn: sqlite3.Connection, account_id: int, initial_cash: float) -> AccountState:
    trades = load_trades(conn, account_id)
    return compute_account_state(initial_cash, trades)


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

    for trade in trades:
        ticker, side, qty, price, fee = _normalize_trade_fields(trade)
        _validate_trade_values(qty, price)

        if side == "buy":
            cash = _apply_buy(ticker, qty, price, fee, positions, avg_cost, cash)
            continue

        if side == "sell":
            cash, realized = _apply_sell(
                ticker,
                qty,
                price,
                fee,
                positions,
                avg_cost,
                cash,
                realized,
            )
            continue

        raise ValueError(f"Unsupported side: {side}")

    positions, avg_cost = _compact_positions(positions, avg_cost)

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
    side, ticker = _normalize_order_input(side, ticker)

    existing_state = _account_state_from_db(conn, account["id"], account["initial_cash"])
    _ensure_sufficient_cash_for_buy(side, qty, price, fee, existing_state.cash)

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
