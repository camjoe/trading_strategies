"""Sleeve risk-gate default limits and sector reference vocabulary.

These are the default values for :class:`SleeveRiskGateConfig`; callers may
override any of them per evaluation.  They live in the models layer because they
are the data-contract defaults the config carries, mirroring how
``SleeveRotationScoreWeights`` keeps its default weights.
"""

from __future__ import annotations

# Default share of a sleeve's equity that any single symbol position may occupy.
DEFAULT_MAX_SLEEVE_NOTIONAL_PCT = 0.25
# Default share of total portfolio equity that any single symbol may occupy.
DEFAULT_MAX_SYMBOL_CONCENTRATION_PCT = 0.30
# Default cap on gross exposure as a multiple of total portfolio equity.
DEFAULT_MAX_PORTFOLIO_GROSS_EXPOSURE = 1.0
# Default share of total portfolio equity that any single sector may occupy.
DEFAULT_MAX_SECTOR_CONCENTRATION_PCT = 0.45

# Static symbol→sector reference data used for sector-concentration limits.
DEFAULT_SYMBOL_SECTOR_MAP: dict[str, str] = {
    "AAPL": "technology",
    "MSFT": "technology",
    "NVDA": "technology",
    "GOOGL": "technology",
    "META": "technology",
    "AMZN": "consumer_discretionary",
    "TSLA": "consumer_discretionary",
    "JPM": "financials",
    "JNJ": "healthcare",
    "UNH": "healthcare",
    "XOM": "energy",
    "WMT": "consumer_staples",
    "SPY": "broad_market",
    "QQQ": "broad_market",
    "IWM": "broad_market",
}
