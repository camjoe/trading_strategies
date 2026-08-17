"""What a CLI handler needs from its invocation, rather than from an import.

Handlers call services directly. Only two things cannot be reached that way and
so are carried here: the database path, and the market-data provider.

The provider is built once per invocation on purpose. An optimizer sweep runs a
backtest per candidate per window, all through the one instance, which is what
makes the adapter's cumulative call guard mean anything — a provider rebuilt per
call would reset the count it is guarding.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trading.services.market_data.protocols import MarketDataProvider


@dataclass(frozen=True, slots=True)
class CliContext:
    db_path: Path
    provider: MarketDataProvider
    # Optimizer runs persist the provider by name rather than holding the instance.
    provider_name: str
