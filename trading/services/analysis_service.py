"""Performance analysis service — read-only portfolio evaluation.

Computes per-account performance metrics, position breakdowns,
and improvement notes for learning/review purposes.
"""
from __future__ import annotations

import sqlite3

from common.constants import SETTLEMENT_TICKER as _SETTLEMENT_TICKER
from trading.domain.accounting import compute_account_state
from trading.models import AccountState
from trading.services.accounting_service import load_trades
from trading.services.reporting_service import (
    benchmark_stats,
    compute_market_value_and_unrealized,
    fetch_latest_prices,
    strategy_return_pct,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Number of top/bottom positions to surface in the analysis summary.
TOP_POSITIONS_COUNT = 5

# Flag a position as "concentrated" if it exceeds this share of total portfolio.
CONCENTRATION_THRESHOLD_PCT = 20.0

# Minimum unrealized-loss % before a position is called out in improvement notes.
NOTABLE_LOSS_THRESHOLD_PCT = -5.0

# Minimum alpha gap before we comment on benchmark underperformance.
ALPHA_COMMENT_THRESHOLD_PCT = 0.5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_position_analysis(
    state: AccountState,
    prices: dict[str, float],
    total_equity: float,
) -> list[dict[str, float | str]]:
    result = []
    for ticker, qty in sorted(state.positions.items()):
        if qty <= 0:
            continue
        avg_cost = state.avg_cost.get(ticker, 0.0)
        market_price = prices.get(ticker, 0.0)
        market_value = qty * market_price if market_price else 0.0
        unrealized_pnl = (market_price - avg_cost) * qty if market_price else 0.0
        cost_basis = avg_cost * qty
        unrealized_pnl_pct = (
            ((market_price / avg_cost) - 1.0) * 100.0
            if avg_cost > 0 and market_price > 0
            else 0.0
        )
        portfolio_pct = (
            (market_value / total_equity * 100.0)
            if total_equity > 0 and market_price > 0
            else 0.0
        )
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


def _generate_improvement_notes(
    account_return_pct: float,
    benchmark_return_pct: float | None,
    alpha: float | None,
    position_analysis: list[dict[str, float | str]],
    realized_pnl: float,
) -> list[str]:
    notes: list[str] = []

    # Benchmark comparison
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
                f"Roughly in line with the benchmark: {account_return_pct:.1f}% vs "
                f"{benchmark_return_pct:.1f}%."
            )

    # Concentration risk
    concentrated = [
        p for p in position_analysis
        if float(p["portfolioPct"]) > CONCENTRATION_THRESHOLD_PCT
    ]
    if concentrated:
        names = ", ".join(str(p["ticker"]) for p in concentrated)
        notes.append(
            f"Concentration risk: {names} each exceed "
            f"{CONCENTRATION_THRESHOLD_PCT:.0f}% of your portfolio. "
            "Large single-position exposure amplifies drawdown risk."
        )

    # Worst performer
    ranked = sorted(
        [p for p in position_analysis if float(p["marketPrice"]) > 0],
        key=lambda p: float(p["unrealizedPnlPct"]),
    )
    if ranked and float(ranked[0]["unrealizedPnlPct"]) < NOTABLE_LOSS_THRESHOLD_PCT:
        worst = ranked[0]
        notes.append(
            f"{worst['ticker']} is your worst performer at "
            f"{float(worst['unrealizedPnlPct']):.1f}% unrealized. "
            "Review whether the original thesis still holds."
        )

    # Realized PnL comment
    if realized_pnl < 0:
        notes.append(
            f"${abs(realized_pnl):.2f} in realized losses (likely expired options). "
            "Review options sizing and expiry selection to reduce premium decay drag."
        )
    elif realized_pnl > 0:
        notes.append(
            f"${realized_pnl:.2f} in realized gains — good discipline on the exits."
        )

    # Buy-and-hold reminder
    equity_positions = [
        p for p in position_analysis
        if ";instrument=option" not in str(p.get("ticker", ""))
    ]
    if equity_positions:
        notes.append(
            "All equity positions remain open with no closes. "
            "Consider whether trailing stops or partial profit-takes would "
            "lock in gains on your strongest winners."
        )

    return notes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_account_analysis(
    conn: sqlite3.Connection,
    account_row: sqlite3.Row,
) -> dict[str, object]:
    """Return a full performance analysis dict for an account.

    Loads trades, computes state and live prices, benchmarks against
    the account's ``benchmark_ticker``, and generates improvement notes.

    When ``initial_cash`` is ``0`` (deposit-model accounts), the return
    percentage denominator falls back to ``state.total_deposited`` — the
    cumulative cash injected via settlement-ticker (``CASH``) buy trades.
    """
    from common.coercion import row_expect_float, row_expect_str
    account_id = int(account_row["id"])
    initial_cash = row_expect_float(account_row, "initial_cash")
    benchmark_ticker = row_expect_str(account_row, "benchmark_ticker")
    created_at = row_expect_str(account_row, "created_at")

    trades = load_trades(conn, account_id)
    state = compute_account_state(initial_cash, trades)
    tickers = sorted(state.positions.keys())
    prices = fetch_latest_prices(tickers) if tickers else {}
    market_value, unrealized = compute_market_value_and_unrealized(
        state.positions, state.avg_cost, prices
    )
    equity = state.cash + market_value

    effective_initial = initial_cash if initial_cash else state.total_deposited
    account_return = strategy_return_pct(equity, effective_initial) if effective_initial else 0.0
    _, bench_return = benchmark_stats(benchmark_ticker, effective_initial, created_at)
    alpha = (account_return - bench_return) if bench_return is not None else None

    position_analysis = _compute_position_analysis(state, prices, equity)
    # Exclude settlement fund from investable-position rankings
    ranked = sorted(
        [
            p for p in position_analysis
            if float(p["marketPrice"]) > 0 and str(p["ticker"]) != _SETTLEMENT_TICKER
        ],
        key=lambda p: float(p["unrealizedPnlPct"]),
        reverse=True,
    )

    improvement_notes = _generate_improvement_notes(
        account_return, bench_return, alpha, position_analysis, state.realized_pnl
    )

    return {
        "accountReturnPct": account_return,
        "benchmarkReturnPct": bench_return,
        "alphaPct": alpha,
        "realizedPnl": state.realized_pnl,
        "unrealizedPnl": unrealized,
        "equity": equity,
        "topWinners": ranked[:TOP_POSITIONS_COUNT],
        "topLosers": list(reversed(ranked[-TOP_POSITIONS_COUNT:])),
        "improvementNotes": improvement_notes,
    }
