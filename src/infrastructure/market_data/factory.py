"""Concrete market-data provider factory.

Resolves the configured provider (constructor argument, then
``TRADING_MARKET_DATA_PROVIDER`` env var, then the ``local/market_data_config.json``
file, then the default) and returns a *fresh* instance each call. Holds no
module-level state — composition roots call ``build_provider`` once at entry and
inject the result down the call chain (mirroring the broker factory pattern).

This is the sole location for ``provider`` routing and concrete-adapter
construction. ``src/trading/`` must never import this module; the interface
layer (and the backtest composition seam) wire it in.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

from common.git import get_repo_root
from trading.services.market_data.protocols import MarketDataProvider

from .demo_provider import DemoMarketDataProvider
from .unavailable_provider import UnavailableProvider
from .yfinance_provider import YFinanceProvider

_REPO_ROOT = get_repo_root(__file__)
_DEFAULT_PROVIDER_NAME = "yfinance"
_DEFAULT_MARKET_DATA_CONFIG_PATH = _REPO_ROOT / "local" / "market_data_config.json"

_PROVIDER_FACTORIES: dict[str, Callable[[], MarketDataProvider]] = {
    "demo": DemoMarketDataProvider,
    "yfinance": YFinanceProvider,
    "yahooquery": lambda: UnavailableProvider("yahooquery"),
    "pandas-datareader": lambda: UnavailableProvider("pandas-datareader"),
    "alpha_vantage": lambda: UnavailableProvider("alpha_vantage"),
    "tiingo": lambda: UnavailableProvider("tiingo"),
    "stooq": lambda: UnavailableProvider("stooq"),
    "polygon-api-client": lambda: UnavailableProvider("polygon-api-client"),
    "ccxt": lambda: UnavailableProvider("ccxt"),
}


def supported_provider_names() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDER_FACTORIES))


def _supported_provider_text() -> str:
    return ", ".join(sorted(_PROVIDER_FACTORIES))


def _provider_factory(name: str) -> Callable[[], MarketDataProvider]:
    factory = _PROVIDER_FACTORIES.get(name)
    if factory is None:
        raise ValueError(f"Unsupported market data provider '{name}'. Supported values: {_supported_provider_text()}")
    return factory


def _config_path() -> Path:
    raw = str(os.getenv("TRADING_MARKET_DATA_CONFIG", "")).strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _DEFAULT_MARKET_DATA_CONFIG_PATH


def _provider_name_from_file(config_path: Path) -> str | None:
    if not config_path.exists():
        return None
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    value = str(payload.get("provider", "")).strip().lower()
    return value or None


def resolve_provider_name() -> str:
    """Resolve the configured provider name from env, then file, then default."""
    env_name = str(os.getenv("TRADING_MARKET_DATA_PROVIDER", "")).strip().lower()
    if env_name:
        return env_name

    file_name = _provider_name_from_file(_config_path())
    if file_name:
        return file_name

    return _DEFAULT_PROVIDER_NAME


def build_provider(name: str | None = None) -> MarketDataProvider:
    """Build a fresh ``MarketDataProvider``.

    When *name* is ``None`` the provider is resolved from configuration
    (env var, then config file, then the default). Raises ``ValueError`` for an
    unsupported name.
    """
    resolved = name.strip().lower() if name else resolve_provider_name()
    return _provider_factory(resolved)()
