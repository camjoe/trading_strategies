import sqlite3

try:
    from trading.accounts import get_account, utc_now_iso
    from trading.accounting import compute_account_state, load_trades
    from trading.pricing import benchmark_stats, fetch_latest_prices
except ModuleNotFoundError:
    from accounts import get_account, utc_now_iso
    from accounting import compute_account_state, load_trades
    from pricing import benchmark_stats, fetch_latest_prices


def format_goal_text(row: sqlite3.Row) -> str:
    if row["goal_min_return_pct"] is None and row["goal_max_return_pct"] is None:
        return "not-set"
    if row["goal_min_return_pct"] is not None and row["goal_max_return_pct"] is not None:
        return (
            f"{float(row['goal_min_return_pct']):.2f}% to "
            f"{float(row['goal_max_return_pct']):.2f}% per {row['goal_period']}"
        )
    if row["goal_min_return_pct"] is not None:
        return f">= {float(row['goal_min_return_pct']):.2f}% per {row['goal_period']}"
    return f"<= {float(row['goal_max_return_pct']):.2f}% per {row['goal_period']}"


def build_account_stats(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
) -> tuple[object, dict[str, float], float, float, float]:
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

    goal_text = format_goal_text(account)

    print(f"Account: {account['name']} | Strategy: {account['strategy']}")
    print(f"Descriptive Name: {account['descriptive_name']}")
    print(f"Benchmark: {account['benchmark_ticker']}")
    print(f"Goal: {goal_text}")
    print(f"Learning Enabled: {'yes' if int(account['learning_enabled']) else 'no'}")
    print(f"Risk Policy: {account['risk_policy']}")
    print(f"Instrument Mode: {account['instrument_mode']}")
    if account["instrument_mode"] == "leaps":
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
         SELECT id, name, descriptive_name, strategy, initial_cash, created_at, benchmark_ticker,
             goal_min_return_pct, goal_max_return_pct, goal_period, learning_enabled,
             risk_policy, instrument_mode
        FROM accounts
        ORDER BY strategy, name
        """
    ).fetchall()

    if not accounts:
        print("No paper accounts found.")
        return

    print("Per-strategy comparison:")
    for account in accounts:
        state, _prices, _market_value, _unrealized, equity = build_account_stats(conn, account)
        strategy_return_pct = ((equity / account["initial_cash"]) - 1.0) * 100.0
        bench_equity, bench_return_pct = benchmark_stats(
            account["benchmark_ticker"], account["initial_cash"], account["created_at"]
        )
        trend = infer_overall_trend(conn, account["id"], equity, lookback)

        position_count = len(state.positions)
        if state.positions:
            sorted_positions = sorted(state.positions.items(), key=lambda x: x[0])
            positions_text = ", ".join([f"{k}:{v:.2f}" for k, v in sorted_positions[:5]])
            if len(sorted_positions) > 5:
                positions_text += ", ..."
        else:
            positions_text = "none"

        print(
            f"- {account['name']} ({account['descriptive_name']}) | strategy={account['strategy']} | "
            f"benchmark={account['benchmark_ticker']} | learning={'on' if int(account['learning_enabled']) else 'off'} | "
            f"risk={account['risk_policy']} | mode={account['instrument_mode']}"
        )
        print(f"  goal={format_goal_text(account)}")
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
