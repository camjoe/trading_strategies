"""Pure ledger computation — no I/O, no repository calls."""
import sqlite3
from collections import defaultdict

from trading.models import AccountState

VALID_SIDES = {"buy", "sell"}

# Ticker used for cash deposits/withdrawals. Buys are inflows (no position created).
SETTLEMENT_TICKER = "CASH"


def _normalize_trade_fields(trade: sqlite3.Row) -> tuple[str, str, float, float, float]:
    return (
        str(trade["ticker"]).upper(),
        str(trade["side"]).lower(),
        float(trade["qty"]),
        float(trade["price"]),
        float(trade["fee"]),
    )


def _validate_trade_values(qty: float, price: float, *, side: str = "buy") -> None:
    if qty <= 0:
        raise ValueError("Trade quantity must be > 0.")
    # Sells at $0 are valid (e.g. expired options); buys must have a positive price.
    if side == "buy" and price <= 0:
        raise ValueError("Trade price must be > 0.")
    if price < 0:
        raise ValueError("Trade price must be >= 0.")


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


def _apply_trade_to_state(
    trade: sqlite3.Row,
    positions: dict[str, float],
    avg_cost: dict[str, float],
    cash: float,
    realized: float,
    total_deposited: float,
    settlement_ticker: str | None,
) -> tuple[float, float, float]:
    ticker, side, qty, price, fee = _normalize_trade_fields(trade)
    _validate_trade_values(qty, price, side=side)
    if settlement_ticker and ticker == settlement_ticker:
        # Settlement ticker buys are cash deposits (inflow); sells are withdrawals.
        if side == "buy":
            deposit = qty * price
            return cash + deposit, realized, total_deposited + deposit
        if side == "sell":
            return cash - (qty * price + fee), realized, total_deposited
    if side == "buy":
        return _apply_buy(ticker, qty, price, fee, positions, avg_cost, cash), realized, total_deposited
    if side == "sell":
        new_cash, new_realized = _apply_sell(ticker, qty, price, fee, positions, avg_cost, cash, realized)
        return new_cash, new_realized, total_deposited
    raise ValueError(f"Unsupported side: {side}")


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


def compute_account_state(
    initial_cash: float,
    trades: list[sqlite3.Row],
    settlement_ticker: str | None = SETTLEMENT_TICKER,
) -> AccountState:
    """Replay a trade list and return the resulting ``AccountState``.

    Parameters
    ----------
    initial_cash:
        Starting cash balance.  Set to ``0.0`` for accounts that seed capital
        exclusively through deposit trades (see ``settlement_ticker``).
    trades:
        Ordered list of trade rows from the ``trades`` table.  Each row must
        expose ``ticker``, ``side``, ``qty``, ``price``, and ``fee`` keys.
    settlement_ticker:
        Ticker reserved for cash deposits and withdrawals.  Defaults to
        :data:`SETTLEMENT_TICKER` (``"CASH"``).  A *buy* on this ticker adds
        ``qty * price`` to ``state.cash`` and ``state.total_deposited`` instead
        of creating a position; a *sell* subtracts the notional value from
        ``state.cash``.  Pass ``None`` to disable this behaviour and treat every
        ticker as a regular equity.
    """
    positions: dict[str, float] = defaultdict(float)
    avg_cost: dict[str, float] = defaultdict(float)
    cash = float(initial_cash)
    realized = 0.0
    total_deposited = 0.0
    for trade in trades:
        cash, realized, total_deposited = _apply_trade_to_state(
            trade, positions, avg_cost, cash, realized, total_deposited, settlement_ticker
        )
    positions, avg_cost = _compact_positions(positions, avg_cost)
    return AccountState(
        cash=cash,
        positions=positions,
        avg_cost=avg_cost,
        realized_pnl=realized,
        total_deposited=total_deposited,
    )
