from __future__ import annotations

import random
import sqlite3
from typing import Callable, Mapping, Protocol, cast


class AccountStateLike(Protocol):
    positions: Mapping[str, float]


def refresh_account_state(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    *,
    compute_account_state_fn: Callable[[float, list[sqlite3.Row]], object],
    load_trades_fn: Callable[[sqlite3.Connection, int], list[sqlite3.Row]],
):
    return compute_account_state_fn(account["initial_cash"], load_trades_fn(conn, account["id"]))


def prepare_trade_selection(
    account: sqlite3.Row,
    active_strategy: str | None,
    state,
    can_sell: list[str],
    forced_sell: str | None,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    learning_enabled: bool,
    instrument_mode: str,
    fee: float,
    *,
    choose_side_fn: Callable[[str | None, list[str], str | None], str],
    prepare_buy_trade_fn: Callable[..., tuple[str, int, float, float | None, float | None] | None],
    prepare_sell_trade_fn: Callable[..., tuple[str, int, float] | None],
) -> tuple[str, str, int, float, float | None, float | None] | None:
    side = choose_side_fn(forced_sell, can_sell, active_strategy)

    delta_est: float | None = None
    iv_est: float | None = None

    if side == "buy":
        prepared_buy = prepare_buy_trade_fn(
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
            return None
        ticker, qty, trade_price, delta_est, iv_est = prepared_buy
    else:
        prepared_sell = prepare_sell_trade_fn(
            can_sell,
            forced_sell,
            prices,
            state,
            learning_enabled,
            instrument_mode,
        )
        if prepared_sell is None:
            return None
        ticker, qty, trade_price = prepared_sell

    return side, ticker, qty, trade_price, delta_est, iv_est


def record_prepared_trade(
    conn: sqlite3.Connection,
    account_name: str,
    account: sqlite3.Row,
    learning_enabled: bool,
    risk_policy: str,
    instrument_mode: str,
    active_strategy: str | None,
    fee: float,
    selection: tuple[str, str, int, float, float | None, float | None],
    forced_sell: str | None,
    *,
    record_trade_fn: Callable[..., None],
    utc_now_iso_fn: Callable[[], str],
    build_trade_note_fn: Callable[..., str],
) -> None:
    side, ticker, qty, trade_price, delta_est, iv_est = selection
    record_trade_fn(
        conn,
        account_name=account_name,
        side=side,
        ticker=ticker,
        qty=qty,
        price=trade_price,
        fee=fee,
        trade_time=utc_now_iso_fn(),
        note=build_trade_note_fn(
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


def run_for_account(
    conn: sqlite3.Connection,
    account_name: str,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    min_trades: int,
    max_trades: int,
    fee: float,
    *,
    get_account_fn: Callable[[sqlite3.Connection, str], sqlite3.Row],
    utc_now_iso_fn: Callable[[], str],
    rotate_account_if_due_fn: Callable[[sqlite3.Connection, str, sqlite3.Row, str], sqlite3.Row],
    resolve_active_strategy_fn: Callable[[sqlite3.Row], str],
    refresh_account_state_fn: Callable[[sqlite3.Connection, sqlite3.Row], AccountStateLike],
    resolve_forced_sell_ticker_fn: Callable[..., str | None],
    prepare_trade_selection_fn: Callable[..., tuple[str, str, int, float, float | None, float | None] | None],
    record_prepared_trade_fn: Callable[..., None],
) -> int:
    account = get_account_fn(conn, account_name)
    now_iso = utc_now_iso_fn()
    account = rotate_account_if_due_fn(conn, account_name, account, now_iso)
    active_strategy = resolve_active_strategy_fn(account)
    learning_enabled = bool(
        int(cast(int | float | str | bytes | bytearray, account["learning_enabled"] or 0))
    )
    risk_policy = str(account["risk_policy"]).strip().lower()
    stop_loss_pct = account["stop_loss_pct"]
    take_profit_pct = account["take_profit_pct"]
    instrument_mode = str(account["instrument_mode"]).strip().lower()
    target = random.randint(min_trades, max_trades)
    executed = 0
    for _ in range(target):
        state = refresh_account_state_fn(conn, account)
        can_sell = [ticker for ticker, qty in state.positions.items() if qty >= 1]
        forced_sell = resolve_forced_sell_ticker_fn(
            can_sell,
            prices,
            state,
            risk_policy,
            stop_loss_pct,
            take_profit_pct,
        )

        selection = prepare_trade_selection_fn(
            account,
            active_strategy,
            state,
            can_sell,
            forced_sell,
            universe,
            prices,
            iv_rank_proxy,
            learning_enabled,
            instrument_mode,
            fee,
        )
        if selection is None:
            continue

        record_prepared_trade_fn(
            conn,
            account_name,
            account,
            learning_enabled,
            risk_policy,
            instrument_mode,
            active_strategy,
            fee,
            selection,
            forced_sell,
        )
        executed += 1

    return executed
