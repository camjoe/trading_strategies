"""Risk-adjusted performance ratios over a series of periodic returns.

Pure Python on purpose. The live runtime scores a book's recent sessions and the
backtester scores a simulated equity curve; both need the same Sharpe, and
``trading`` does not depend on pandas. The backtester converts its series at the
boundary rather than this module reaching for a dataframe.
"""

from __future__ import annotations

from collections.abc import Sequence

from common.constants import ANNUALIZATION_FACTOR, TRADING_DAYS_PER_YEAR


def sharpe_ratio(returns: Sequence[float], *, risk_free_rate: float = 0.0) -> float | None:
    """Annualized Sharpe ratio over *returns*, each a fractional periodic return.

    ``risk_free_rate`` is an annual rate, spread across the trading year to match
    the grain of the returns. Answers ``None`` when there are no returns or they
    have no dispersion — a zero-volatility Sharpe is undefined, not infinite.

    Uses the population standard deviation (``ddof=0``), so a series and the same
    series read through pandas agree.
    """
    if not returns:
        return None
    periodic_risk_free_rate = risk_free_rate / float(TRADING_DAYS_PER_YEAR)
    excess = [value - periodic_risk_free_rate for value in returns]
    mean = sum(excess) / len(excess)
    variance = sum((value - mean) ** 2 for value in excess) / len(excess)
    standard_deviation = variance**0.5
    if standard_deviation <= 0:
        return None
    return mean / standard_deviation * ANNUALIZATION_FACTOR
