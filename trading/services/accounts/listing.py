from __future__ import annotations

import sqlite3

from trading.models import AccountRecord
from trading.domain.auto_trading_policy import DEFAULT_MAX_POSITION_PCT, DEFAULT_TRADE_SIZE_PCT
from trading.repositories.accounts import fetch_account_listing_rows

HEURISTIC_EXPLORATION_LABEL = "heuristic_exploration"
GOAL_NOT_SET_TEXT = "not-set"


def format_goal_text(row: AccountRecord) -> str:
    min_goal = row.goal_min_return_pct
    max_goal = row.goal_max_return_pct
    goal_period = row.goal_period or "period"
    if min_goal is None and max_goal is None:
        return GOAL_NOT_SET_TEXT
    if min_goal is not None and max_goal is not None:
        return f"{min_goal:.2f}% to {max_goal:.2f}% per {goal_period}"
    if min_goal is not None:
        return f">= {min_goal:.2f}% per {goal_period}"
    return f"<= {max_goal:.2f}% per {goal_period}"


def _resolve_base_and_active_strategy(row: AccountRecord) -> tuple[str, str]:
    base_strategy = row.strategy
    rotation_enabled = bool(row.rotation_enabled)
    if not rotation_enabled:
        return base_strategy, base_strategy

    active_strategy = row.rotation_active_strategy or base_strategy
    return base_strategy, active_strategy


def format_account_policy_text(row: AccountRecord) -> str:
    base_strategy, active_strategy = _resolve_base_and_active_strategy(row)
    learning_enabled = row.learning_enabled
    trade_size_pct = row.trade_size_pct
    max_position_pct = row.max_position_pct
    benchmark_ticker = row.benchmark_ticker
    risk_policy = row.risk_policy
    instrument_mode = row.instrument_mode
    resolved_trade_size_pct = trade_size_pct if trade_size_pct is not None else DEFAULT_TRADE_SIZE_PCT
    resolved_max_position_pct = max_position_pct if max_position_pct is not None else DEFAULT_MAX_POSITION_PCT
    return (
        f"base_strategy={base_strategy} | active_strategy={active_strategy} | "
        f"benchmark={benchmark_ticker} | "
        f"{HEURISTIC_EXPLORATION_LABEL}={'on' if learning_enabled else 'off'} | "
        f"risk={risk_policy} | instrument={instrument_mode} | "
        f"trade_size={resolved_trade_size_pct:.2f}% | max_position={resolved_max_position_pct:.2f}%"
    )


def build_account_summary_line(row: AccountRecord) -> str:
    initial_cash = row.initial_cash
    initial_cash_text = f"{initial_cash:.2f}" if initial_cash is not None else "n/a"
    policy_text = format_account_policy_text(row)
    summary = (
        f"[{row.id}] {row.name} | display_name={row.descriptive_name} | "
        f"initial_cash={initial_cash_text} | account_policy={policy_text} | "
        f"created={row.created_at}"
    )
    goal_text = format_goal_text(row)
    if goal_text != GOAL_NOT_SET_TEXT:
        return f"{summary} | goal_metadata={goal_text}"
    return summary


def build_account_listing_lines(accounts: list[AccountRecord], *, by_strategy: bool) -> list[str]:
    lines: list[str] = []
    if by_strategy:
        current_strategy = None
        for account in accounts:
            strategy = account.strategy
            if strategy != current_strategy:
                if current_strategy is not None:
                    lines.append("")
                current_strategy = strategy
                lines.append(f"Base Strategy: {current_strategy}")
            lines.append(f"  {build_account_summary_line(account)}")
        return lines
    for account in accounts:
        lines.append(build_account_summary_line(account))
    return lines


def list_accounts(conn: sqlite3.Connection, by_strategy: bool = True) -> None:
    accounts = fetch_account_listing_rows(conn)
    if not accounts:
        print("No paper accounts found.")
        return
    for line in build_account_listing_lines(accounts, by_strategy=by_strategy):
        print(line)
