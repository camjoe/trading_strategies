"""Pure portfolio-return math shared across analysis and reporting.

Side-effect-free equity/return/alpha helpers. These are domain policy math
(no I/O, no persistence), consumed by ``services.analysis`` payload flows and
``services.reporting`` presentation flows alike, so they live at the domain
layer where both can reach them without an upward import.
"""

from __future__ import annotations

from trading.domain.returns import total_return_pct


def compute_market_value_and_unrealized(
    positions: dict[str, float],
    avg_cost: dict[str, float],
    prices: dict[str, float],
) -> tuple[float, float]:
    market_value = 0.0
    unrealized = 0.0
    for ticker, qty in positions.items():
        price = prices.get(ticker)
        if price is None:
            continue
        market_value += qty * price
        unrealized += (price - avg_cost.get(ticker, 0.0)) * qty
    return market_value, unrealized


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
    "compute_market_value_and_unrealized",
    "strategy_return_pct",
]
