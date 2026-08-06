"""Universe service package — expands named universe identifiers to ticker lists."""

from __future__ import annotations

from trading.services.universe.resolver import (
    DEFAULT_TICKERS_FILE,
    DEFAULT_UNIVERSE_NAME,
    default_trade_symbols,
    list_available_universes,
    resolve_named_universes,
    resolve_trade_symbols,
)

__all__ = [
    "DEFAULT_TICKERS_FILE",
    "DEFAULT_UNIVERSE_NAME",
    "default_trade_symbols",
    "list_available_universes",
    "resolve_named_universes",
    "resolve_trade_symbols",
]
