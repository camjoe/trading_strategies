import sqlite3
from common.time import utc_now_iso
from trading.accounts import get_account
from trading.accounting import compute_account_state, load_trades
from trading.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_int
from trading.models import AccountState
from trading.pricing import benchmark_stats, fetch_latest_prices
from trading.repositories import (
    fetch_account_listing_rows,
    fetch_recent_equity_rows,
    fetch_snapshot_history_rows,
    insert_snapshot_row,
)
from trading.services.accounts_service import format_goal_text
from trading.services.reporting_service import (
    alpha_pct,
    benchmark_available,
    build_account_stats as build_account_stats_impl,
    infer_overall_trend as infer_overall_trend_impl,
    positions_summary_text,
    strategy_return_pct,
)


def _print_leaps_params(account: sqlite3.Row) -> None:
    print(
        "LEAPs Params: "
        f"strike_offset_pct={account['option_strike_offset_pct']} "
        f"min_dte={account['option_min_dte']} max_dte={account['option_max_dte']}"
    )
    print(
        "Options Filters: "
        f"type={account['option_type']} "
        f"delta={account['target_delta_min']}-{account['target_delta_max']} "
        f"iv_rank={account['iv_rank_min']}-{account['iv_rank_max']}"
    )
    print(
        "Options Risk: "
        f"max_premium={account['max_premium_per_trade']} "
        f"max_contracts={account['max_contracts_per_trade']} "
        f"roll_dte={account['roll_dte_threshold']} "
        f"profit_take={account['profit_take_pct']} "
        f"max_loss={account['max_loss_pct']}"
    )


def _print_account_header(account: sqlite3.Row) -> None:
    print(f"Account: {account['name']} | Strategy: {account['strategy']}")
    print(f"Descriptive Name: {account['descriptive_name']}")
    print(f"Benchmark: {account['benchmark_ticker']}")
    print(f"Goal: {format_goal_text(account)}")
    print(f"Learning Enabled: {'yes' if row_int(account, 'learning_enabled') else 'no'}")
    print(f"Risk Policy: {account['risk_policy']}")
    print(f"Instrument Mode: {account['instrument_mode']}")
    if account["instrument_mode"] == "leaps":
        _print_leaps_params(account)


def _print_performance_lines(
    account: sqlite3.Row,
    cash: float,
    market_value: float,
    equity: float,
    realized_pnl: float,
    unrealized: float,
    strategy_return_pct: float,
    benchmark_equity: float | None,
    benchmark_return_pct: float | None,
) -> None:
    initial_cash = row_float(account, "initial_cash")
    print(f"Initial Cash: {initial_cash:.2f}" if initial_cash is not None else "Initial Cash: N/A")
    print(f"Cash: {cash:.2f}")
    print(f"Market Value: {market_value:.2f}")
    print(f"Equity: {equity:.2f}")
    print(f"Strategy Return %: {strategy_return_pct:.2f}")
    print(f"Realized PnL: {realized_pnl:.2f}")
    print(f"Unrealized PnL: {unrealized:.2f}")

    if benchmark_available(benchmark_equity, benchmark_return_pct):
        assert benchmark_return_pct is not None
        assert benchmark_equity is not None
        alpha_value = alpha_pct(strategy_return_pct, benchmark_return_pct)
        print(f"Benchmark Equity: {benchmark_equity:.2f}")
        print(f"Benchmark Return %: {benchmark_return_pct:.2f}")
        print(f"Strategy Alpha vs Benchmark %: {alpha_value:.2f}")
        return

    print("Benchmark comparison: unavailable (price history not found)")


def _print_open_positions(
    positions: dict[str, float],
    avg_cost: dict[str, float],
    prices: dict[str, float],
) -> None:
    if not positions:
        print("Open Positions: none")
        return

    print("Open Positions:")
    for ticker in sorted(positions.keys()):
        qty = positions[ticker]
        avg = avg_cost[ticker]
        px = prices.get(ticker)
        px_display = f"{px:.2f}" if px is not None else "N/A"
        print(f"- {ticker}: qty={qty:.4f}, avg_cost={avg:.2f}, last_price={px_display}")


def _compare_account_header(account: sqlite3.Row) -> str:
    learning = row_int(account, "learning_enabled")
    return (
        f"- {account['name']} ({account['descriptive_name']}) | strategy={account['strategy']} | "
        f"benchmark={account['benchmark_ticker']} | learning={'on' if learning else 'off'} | "
        f"risk={account['risk_policy']} | mode={account['instrument_mode']}"
    )


def _compare_benchmark_line(
    strategy_return_pct: float,
    benchmark_equity: float | None,
    benchmark_return_pct: float | None,
) -> str:
    if benchmark_available(benchmark_equity, benchmark_return_pct):
        assert benchmark_equity is not None
        assert benchmark_return_pct is not None
        alpha_value = alpha_pct(strategy_return_pct, benchmark_return_pct)
        return (
            f"  benchmark_equity={benchmark_equity:.2f} benchmark_return={benchmark_return_pct:.2f}% "
            f"alpha={alpha_value:.2f}%"
        )
    return "  benchmark_equity=N/A benchmark_return=N/A alpha=N/A"


def build_account_stats(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
) -> tuple[AccountState, dict[str, float], float, float, float]:
    state, prices, market_value, unrealized, equity = build_account_stats_impl(
        conn,
        account,
        load_trades_fn=load_trades,
        compute_account_state_fn=compute_account_state,
        fetch_latest_prices_fn=fetch_latest_prices,
        row_expect_int_fn=row_expect_int,
        row_expect_float_fn=row_expect_float,
    )
    return state, prices, market_value, unrealized, equity


def infer_overall_trend(
    conn: sqlite3.Connection,
    account_id: int,
    current_equity: float,
    lookback: int,
) -> str:
    return infer_overall_trend_impl(
        conn,
        account_id,
        current_equity,
        lookback,
        fetch_recent_equity_rows_fn=fetch_recent_equity_rows,
        row_float_fn=row_float,
    )


def account_report(conn: sqlite3.Connection, account_name: str) -> tuple[dict[str, float], dict[str, float]]:
    account = get_account(conn, account_name)
    state, prices, market_value, unrealized, equity = build_account_stats(conn, account)
    benchmark_ticker = row_expect_str(account, "benchmark_ticker")
    initial_cash = row_expect_float(account, "initial_cash")
    created_at = row_expect_str(account, "created_at")
    benchmark_equity, benchmark_return_pct = benchmark_stats(
        benchmark_ticker, initial_cash, created_at
    )
    strategy_return_pct_value = strategy_return_pct(equity, initial_cash)

    _print_account_header(account)
    _print_performance_lines(
        account,
        state.cash,
        market_value,
        equity,
        state.realized_pnl,
        unrealized,
        strategy_return_pct_value,
        benchmark_equity,
        benchmark_return_pct,
    )
    _print_open_positions(state.positions, state.avg_cost, prices)

    stats = {
        "cash": state.cash,
        "market_value": market_value,
        "equity": equity,
        "realized_pnl": state.realized_pnl,
        "unrealized_pnl": unrealized,
        "strategy_return_pct": strategy_return_pct_value,
    }
    return stats, state.positions


def compare_strategies(conn: sqlite3.Connection, lookback: int) -> None:
    accounts = fetch_account_listing_rows(conn)

    if not accounts:
        print("No paper accounts found.")
        return

    print("Per-strategy comparison:")
    for account in accounts:
        state, _prices, _market_value, _unrealized, equity = build_account_stats(conn, account)
        initial_cash = row_expect_float(account, "initial_cash")
        benchmark_ticker = row_expect_str(account, "benchmark_ticker")
        created_at = row_expect_str(account, "created_at")
        account_id = row_expect_int(account, "id")
        strategy_return_pct_value = strategy_return_pct(equity, initial_cash)
        bench_equity, bench_return_pct = benchmark_stats(
            benchmark_ticker, initial_cash, created_at
        )
        trend = infer_overall_trend(conn, account_id, equity, lookback)

        position_count, positions_text = positions_summary_text(state.positions)

        print(_compare_account_header(account))
        print(f"  goal={format_goal_text(account)}")
        print(
            f"  equity={equity:.2f} return={strategy_return_pct_value:.2f}% "
            f"positions={position_count} trend={trend}"
        )
        print(_compare_benchmark_line(strategy_return_pct_value, bench_equity, bench_return_pct))
        print(f"  positions: {positions_text}")


def snapshot_account(conn: sqlite3.Connection, account_name: str, snapshot_time: str | None) -> None:
    account = get_account(conn, account_name)
    stats, _ = account_report(conn, account_name)
    insert_snapshot_row(
        conn,
        account_id=account["id"],
        snapshot_time=snapshot_time or utc_now_iso(),
        cash=stats["cash"],
        market_value=stats["market_value"],
        equity=stats["equity"],
        realized_pnl=stats["realized_pnl"],
        unrealized_pnl=stats["unrealized_pnl"],
    )
    print("Snapshot saved.")


def show_snapshots(conn: sqlite3.Connection, account_name: str, limit: int) -> None:
    account = get_account(conn, account_name)
    rows = fetch_snapshot_history_rows(
        conn,
        account_id=account["id"],
        limit=int(limit),
    )

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
