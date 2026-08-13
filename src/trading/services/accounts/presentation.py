"""Pure string builders for operator-facing account listing output.

These helpers turn account and book records into display strings. They perform
no I/O; the read orchestration that consumes them lives in the sibling
``listing`` module.
"""

from __future__ import annotations

from trading.domain.auto_trading.sizing import DEFAULT_MAX_POSITION_PCT, DEFAULT_TRADE_SIZE_PCT
from trading.models import AccountRecord
from trading.models.books import BookRecord
from trading.services.books.book_assignments import UNASSIGNED_STRATEGY_LABEL

HEURISTIC_EXPLORATION_LABEL = "heuristic_exploration"
GOAL_NOT_SET_TEXT = "not-set"


def render_goal_text(book: BookRecord | None) -> str:
    """Goal metadata line — goals are book columns (revision 0008)."""
    if book is None:
        return GOAL_NOT_SET_TEXT
    min_goal = book.goal_min_return_pct
    max_goal = book.goal_max_return_pct
    goal_period = book.goal_period or "period"
    if min_goal is None and max_goal is None:
        return GOAL_NOT_SET_TEXT
    if min_goal is not None and max_goal is not None:
        return f"{min_goal:.2f}% to {max_goal:.2f}% per {goal_period}"
    if min_goal is not None:
        return f">= {min_goal:.2f}% per {goal_period}"
    return f"<= {max_goal:.2f}% per {goal_period}"


def render_account_policy_text(
    row: AccountRecord,
    *,
    active_strategy: str | None = None,
    book: BookRecord | None = None,
) -> str:
    """Format the policy line; ``active_strategy`` is the default-book
    assignment's strategy (ADR 014). Execution knobs are book columns
    (revision 0004), so ``book`` is the account's default book; without one
    the code defaults are shown. accounts.strategy was dropped in revision
    0008 — the assignment-derived active strategy is the only strategy."""
    active_strategy = active_strategy or UNASSIGNED_STRATEGY_LABEL
    learning_enabled = book.learning_enabled if book is not None else 0
    trade_size_pct = book.trade_size_pct if book is not None else None
    max_position_pct = book.max_position_pct if book is not None else None
    benchmark_ticker = row.benchmark_ticker
    risk_policy = book.risk_policy if book is not None else "none"
    instrument_mode = book.instrument_mode if book is not None else "equity"
    resolved_trade_size_pct = trade_size_pct if trade_size_pct is not None else DEFAULT_TRADE_SIZE_PCT
    resolved_max_position_pct = max_position_pct if max_position_pct is not None else DEFAULT_MAX_POSITION_PCT
    return (
        f"active_strategy={active_strategy} | "
        f"benchmark={benchmark_ticker} | "
        f"{HEURISTIC_EXPLORATION_LABEL}={'on' if learning_enabled else 'off'} | "
        f"risk={risk_policy} | instrument={instrument_mode} | "
        f"trade_size={resolved_trade_size_pct:.2f}% | max_position={resolved_max_position_pct:.2f}%"
    )


def render_account_summary_line(
    row: AccountRecord,
    *,
    active_strategy: str | None = None,
    book: BookRecord | None = None,
) -> str:
    initial_cash = row.initial_cash
    initial_cash_text = f"{initial_cash:.2f}" if initial_cash is not None else "n/a"
    policy_text = render_account_policy_text(row, active_strategy=active_strategy, book=book)
    summary = (
        f"[{row.id}] {row.name} | display_name={row.descriptive_name} | "
        f"initial_cash={initial_cash_text} | account_policy={policy_text} | "
        f"created={row.created_at}"
    )
    goal_text = render_goal_text(book)
    if goal_text != GOAL_NOT_SET_TEXT:
        return f"{summary} | goal_metadata={goal_text}"
    return summary


def render_account_listing_lines(
    accounts: list[AccountRecord],
    *,
    by_strategy: bool,
    active_strategies: dict[int, str] | None = None,
    default_books: dict[int, BookRecord] | None = None,
) -> list[str]:
    resolved = active_strategies or {}
    books = default_books or {}
    lines: list[str] = []
    if by_strategy:
        # Grouping key is the assignment-derived active strategy (revision 0008).
        current_strategy: str | None = None
        for account in sorted(accounts, key=lambda a: (resolved.get(a.id, UNASSIGNED_STRATEGY_LABEL), a.name)):
            strategy = resolved.get(account.id, UNASSIGNED_STRATEGY_LABEL)
            if strategy != current_strategy:
                if current_strategy is not None:
                    lines.append("")
                current_strategy = strategy
                lines.append(f"Strategy: {current_strategy}")
            lines.append(
                "  "
                + render_account_summary_line(
                    account, active_strategy=resolved.get(account.id), book=books.get(account.id)
                )
            )
        return lines
    for account in accounts:
        lines.append(
            render_account_summary_line(account, active_strategy=resolved.get(account.id), book=books.get(account.id))
        )
    return lines


__all__ = [
    "GOAL_NOT_SET_TEXT",
    "HEURISTIC_EXPLORATION_LABEL",
    "render_account_listing_lines",
    "render_account_policy_text",
    "render_goal_text",
]
