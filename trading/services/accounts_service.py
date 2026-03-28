from __future__ import annotations

import sqlite3

from trading.coercion import row_float, row_int, row_str


def format_goal_text(row: sqlite3.Row) -> str:
    min_goal = row_float(row, "goal_min_return_pct")
    max_goal = row_float(row, "goal_max_return_pct")
    goal_period = row_str(row, "goal_period") or "period"
    if min_goal is None and max_goal is None:
        return "not-set"
    if min_goal is not None and max_goal is not None:
        return f"{min_goal:.2f}% to {max_goal:.2f}% per {goal_period}"
    if min_goal is not None:
        return f">= {min_goal:.2f}% per {goal_period}"
    return f"<= {max_goal:.2f}% per {goal_period}"


def build_account_summary_line(row: sqlite3.Row) -> str:
    goal_text = format_goal_text(row)
    initial_cash = row_float(row, "initial_cash")
    learning_enabled = row_int(row, "learning_enabled")
    initial_cash_text = f"{initial_cash:.2f}" if initial_cash is not None else "n/a"
    return (
        f"[{row['id']}] {row['name']} ({row['descriptive_name']}) | strategy={row['strategy']} | "
        f"initial_cash={initial_cash_text} | benchmark={row['benchmark_ticker']} | "
        f"goal={goal_text} | learning={'on' if learning_enabled else 'off'} | "
        f"risk={row['risk_policy']} | instrument={row['instrument_mode']} | "
        f"created={row['created_at']}"
    )


def build_account_listing_lines(accounts: list[sqlite3.Row], *, by_strategy: bool) -> list[str]:
    lines: list[str] = []
    if by_strategy:
        current_strategy = None
        for account in accounts:
            if account["strategy"] != current_strategy:
                if current_strategy is not None:
                    lines.append("")
                current_strategy = account["strategy"]
                lines.append(f"Strategy: {current_strategy}")
            lines.append(f"  {build_account_summary_line(account)}")
        return lines

    for account in accounts:
        lines.append(build_account_summary_line(account))
    return lines