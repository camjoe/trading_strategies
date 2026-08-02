"""Analysis calculation helpers for analysis consumers.

Provides pure position-ranking and note-generation helpers used by
``trading.services.analysis`` query flows.
"""

from __future__ import annotations

from trading.models import AccountState

# Number of top/bottom positions to surface in the analysis summary.
TOP_POSITIONS_COUNT = 5

# Flag a position as "concentrated" if it exceeds this share of total portfolio.
CONCENTRATION_THRESHOLD_PCT = 20.0

# Minimum unrealized-loss % before a position is called out in improvement notes.
NOTABLE_LOSS_THRESHOLD_PCT = -5.0

# Minimum alpha gap before we comment on benchmark underperformance.
ALPHA_COMMENT_THRESHOLD_PCT = 0.5


def compute_position_analysis(
    state: AccountState,
    prices: dict[str, float],
    total_equity: float,
) -> list[dict[str, float | str]]:
    result: list[dict[str, float | str]] = []
    for ticker, qty in sorted(state.positions.items()):
        if qty <= 0:
            continue
        avg_cost = state.avg_cost.get(ticker, 0.0)
        market_price = prices.get(ticker, 0.0)
        market_value = qty * market_price if market_price else 0.0
        unrealized_pnl = (market_price - avg_cost) * qty if market_price else 0.0
        cost_basis = avg_cost * qty
        unrealized_pnl_pct = ((market_price / avg_cost) - 1.0) * 100.0 if avg_cost > 0 and market_price > 0 else 0.0
        portfolio_pct = (market_value / total_equity * 100.0) if total_equity > 0 and market_price > 0 else 0.0
        result.append(
            {
                "ticker": ticker,
                "qty": qty,
                "avgCost": avg_cost,
                "costBasis": cost_basis,
                "marketPrice": market_price,
                "marketValue": market_value,
                "unrealizedPnl": unrealized_pnl,
                "unrealizedPnlPct": unrealized_pnl_pct,
                "portfolioPct": portfolio_pct,
            }
        )
    return result


def generate_improvement_notes(
    account_return_pct: float,
    benchmark_return_pct: float | None,
    alpha: float | None,
    position_analysis: list[dict[str, float | str]],
    realized_pnl: float,
) -> list[str]:
    notes: list[str] = []

    if benchmark_return_pct is not None and alpha is not None:
        if alpha < -ALPHA_COMMENT_THRESHOLD_PCT:
            notes.append(
                f"Your account returned {account_return_pct:.1f}% vs the benchmark's "
                f"{benchmark_return_pct:.1f}% — trailing by {abs(alpha):.1f}%. "
                "Consider whether active selection is adding value over a passive index."
            )
        elif alpha > ALPHA_COMMENT_THRESHOLD_PCT:
            notes.append(
                f"Outperforming the benchmark by {alpha:.1f}% "
                f"({account_return_pct:.1f}% vs benchmark {benchmark_return_pct:.1f}%)."
            )
        else:
            notes.append(
                f"Roughly in line with the benchmark: {account_return_pct:.1f}% vs {benchmark_return_pct:.1f}%."
            )

    concentrated = [
        position for position in position_analysis if float(position["portfolioPct"]) > CONCENTRATION_THRESHOLD_PCT
    ]
    if concentrated:
        names = ", ".join(str(position["ticker"]) for position in concentrated)
        notes.append(
            f"Concentration risk: {names} each exceed "
            f"{CONCENTRATION_THRESHOLD_PCT:.0f}% of your portfolio. "
            "Large single-position exposure amplifies drawdown risk."
        )

    ranked = sorted(
        [position for position in position_analysis if float(position["marketPrice"]) > 0],
        key=lambda position: float(position["unrealizedPnlPct"]),
    )
    if ranked and float(ranked[0]["unrealizedPnlPct"]) < NOTABLE_LOSS_THRESHOLD_PCT:
        worst = ranked[0]
        notes.append(
            f"{worst['ticker']} is your worst performer at "
            f"{float(worst['unrealizedPnlPct']):.1f}% unrealized. "
            "Review whether the original thesis still holds."
        )

    if realized_pnl < 0:
        notes.append(
            f"${abs(realized_pnl):.2f} in realized losses (likely expired options). "
            "Review options sizing and expiry selection to reduce premium decay drag."
        )
    elif realized_pnl > 0:
        notes.append(f"${realized_pnl:.2f} in realized gains — good discipline on the exits.")

    equity_positions = [
        position for position in position_analysis if ";instrument=option" not in str(position.get("ticker", ""))
    ]
    if equity_positions:
        notes.append(
            "All equity positions remain open with no closes. "
            "Consider whether trailing stops or partial profit-takes would "
            "lock in gains on your strongest winners."
        )

    return notes


__all__ = [
    "TOP_POSITIONS_COUNT",
    "compute_position_analysis",
    "generate_improvement_notes",
]
