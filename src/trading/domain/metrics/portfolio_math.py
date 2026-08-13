"""Pure portfolio valuation and return math, shared by the live runtime and the backtester.

Side-effect-free equity/return/alpha helpers. These are domain policy math
(no I/O, no persistence), consumed by ``services.analysis`` payload flows,
``services.reporting`` presentation flows, and the backtest simulation alike, so
they live at the domain layer where all three can reach them.

**Two valuation policies live here, and the split is deliberate.**
``compute_market_value_and_unrealized`` is lenient throughout: an unpriced holding
is skipped and a missing cost basis reads as zero, because an account view that
refused to render over one stale price would be useless to an operator. The
separate ``compute_market_value`` / ``compute_unrealized_pnl`` pair is strict:
market value skips what it cannot price (a partial total is still a real subtotal)
while unrealized P&L raises, because a P&L figure quietly missing a holding is a
wrong number rather than an incomplete one. Do not converge them — each context
chose its policy for a reason stated here.
"""

from __future__ import annotations

from trading.domain.metrics.returns import total_return_pct


def compute_market_value_and_unrealized(
    positions: dict[str, float],
    avg_cost: dict[str, float],
    prices: dict[str, float],
) -> tuple[float, float]:
    """Market value and open P&L in one pass, skipping anything unpriced.

    The lenient pair, for operator-facing account views. See the module docstring
    for why this does not share an implementation with the two functions below.
    """
    market_value = 0.0
    unrealized = 0.0
    for ticker, qty in positions.items():
        price = prices.get(ticker)
        if price is None:
            continue
        market_value += qty * price
        unrealized += (price - avg_cost.get(ticker, 0.0)) * qty
    return market_value, unrealized


def compute_market_value(positions: dict[str, float], prices: dict[str, float]) -> float:
    """Total value of *positions* at *prices*, skipping tickers with no price."""
    total = 0.0
    for ticker, qty in positions.items():
        px = prices.get(ticker)
        if px is None:
            continue
        total += qty * px
    return total


def compute_unrealized_pnl(
    positions: dict[str, float],
    avg_cost: dict[str, float],
    marks: dict[str, float],
) -> float:
    """Open P&L across held positions. Raises ``KeyError`` if a holding has no mark.

    Zero-quantity entries are skipped before the mark is read, so a position closed
    earlier in a run does not require a mark it no longer needs.
    """
    total = 0.0
    for ticker, qty in positions.items():
        if qty <= 0:
            continue
        total += (marks[ticker] - avg_cost[ticker]) * qty
    return total


def strategy_return_pct(equity: float, initial_cash: float) -> float:
    """An account's return on its initial cash. Argument order is (equity, basis)."""
    if not initial_cash:
        raise ValueError(f"Cannot compute return %: initial_cash is 0 (equity={equity:.2f})")
    return total_return_pct(first_equity=initial_cash, last_equity=equity)


def benchmark_available(benchmark_equity: float | None, benchmark_return_pct: float | None) -> bool:
    return benchmark_equity is not None and benchmark_return_pct is not None


def alpha_pct(strategy_return_pct_value: float, benchmark_return_pct_value: float) -> float:
    return strategy_return_pct_value - benchmark_return_pct_value


__all__ = [
    "alpha_pct",
    "benchmark_available",
    "compute_market_value",
    "compute_market_value_and_unrealized",
    "compute_unrealized_pnl",
    "strategy_return_pct",
]
