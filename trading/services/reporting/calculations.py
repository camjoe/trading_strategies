"""Reporting calculation helpers for reporting consumers.

Provides side-effect-free portfolio math used by presentation/orchestration
helpers under ``trading.services.reporting``.
"""

from __future__ import annotations

# Compare output shows at most this many individual positions before truncating.
POSITION_SUMMARY_LIMIT = 5


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
    if not initial_cash:
        raise ValueError(f"Cannot compute return %: initial_cash is 0 (equity={equity:.2f})")
    return ((equity / initial_cash) - 1.0) * 100.0


def benchmark_available(benchmark_equity: float | None, benchmark_return_pct: float | None) -> bool:
    return benchmark_equity is not None and benchmark_return_pct is not None


def alpha_pct(strategy_return_pct_value: float, benchmark_return_pct_value: float) -> float:
    return strategy_return_pct_value - benchmark_return_pct_value


def positions_summary_text(positions: dict[str, float]) -> tuple[int, str]:
    position_count = len(positions)
    if not positions:
        return position_count, "none"
    sorted_positions = sorted(positions.items(), key=lambda x: x[0])
    positions_text = ", ".join(
        f"{ticker}:{qty:.2f}"
        for ticker, qty in sorted_positions[:POSITION_SUMMARY_LIMIT]
    )
    if len(sorted_positions) > POSITION_SUMMARY_LIMIT:
        positions_text += ", ..."
    return position_count, positions_text


__all__ = [
    "alpha_pct",
    "benchmark_available",
    "compute_market_value_and_unrealized",
    "positions_summary_text",
    "strategy_return_pct",
]
