from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

from common.paths.repo_paths import get_repo_root

from .features import ProxyFeatureDataProvider
from .protocols import FeatureDataProvider
from .protocols import MarketDataProvider
from .providers import UnavailableProvider
from .providers import YFinanceProvider


_REPO_ROOT = get_repo_root(__file__)
_DEFAULT_PROVIDER_NAME = "yfinance"
_DEFAULT_MARKET_DATA_CONFIG_PATH = _REPO_ROOT / "local" / "market_data_config.json"

_PROVIDER_FACTORIES: dict[str, Callable[[], MarketDataProvider]] = {
    "yfinance": YFinanceProvider,
    "yahooquery": lambda: UnavailableProvider("yahooquery"),
    "pandas-datareader": lambda: UnavailableProvider("pandas-datareader"),
    "alpha_vantage": lambda: UnavailableProvider("alpha_vantage"),
    "tiingo": lambda: UnavailableProvider("tiingo"),
    "stooq": lambda: UnavailableProvider("stooq"),
    "polygon-api-client": lambda: UnavailableProvider("polygon-api-client"),
    "ccxt": lambda: UnavailableProvider("ccxt"),
}

_provider: MarketDataProvider = YFinanceProvider()
_provider_name = _DEFAULT_PROVIDER_NAME
_provider_source = "default"
_provider_config_mtime: float | None = None
_feature_provider: FeatureDataProvider = ProxyFeatureDataProvider()


def _supported_provider_text() -> str:
    return ", ".join(sorted(_PROVIDER_FACTORIES))


def _config_mtime(config_path: Path) -> float | None:
    return config_path.stat().st_mtime if config_path.exists() else None


def _provider_factory(name: str) -> Callable[[], MarketDataProvider]:
    factory = _PROVIDER_FACTORIES.get(name)
    if factory is None:
        raise ValueError(f"Unsupported market data provider '{name}'. Supported values: {_supported_provider_text()}")
    return factory


def _set_provider_state(provider: MarketDataProvider, *, name: str, source: str) -> None:
    global _provider, _provider_name, _provider_source
    _provider = provider
    _provider_name = name
    _provider_source = source


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


def _resolve_provider_name() -> str:
    env_name = str(os.getenv("TRADING_MARKET_DATA_PROVIDER", "")).strip().lower()
    if env_name:
        return env_name

    file_name = _provider_name_from_file(_config_path())
    if file_name:
        return file_name

    return _DEFAULT_PROVIDER_NAME


def _sync_provider_from_config() -> None:
    global _provider_config_mtime

    target_name = _resolve_provider_name()
    factory = _provider_factory(target_name)
    _set_provider_state(factory(), name=target_name, source="config")

    config_path = _config_path()
    _provider_config_mtime = _config_mtime(config_path)


def _maybe_reload_provider_from_config() -> None:
    if _provider_source != "config":
        return

    config_path = _config_path()
    if not config_path.exists():
        if _provider_config_mtime is not None:
            _sync_provider_from_config()
        return

    current_mtime = config_path.stat().st_mtime
    if _provider_config_mtime is None or current_mtime != _provider_config_mtime:
        _sync_provider_from_config()


def get_provider() -> MarketDataProvider:
    _maybe_reload_provider_from_config()
    return _provider


def set_provider(provider: MarketDataProvider) -> None:
    _set_provider_state(provider, name=provider.__class__.__name__, source="manual")


def set_provider_by_name(name: str) -> None:
    key = name.strip().lower()
    factory = _provider_factory(key)
    _set_provider_state(factory(), name=key, source="manual")


def reload_provider_from_config() -> str:
    _sync_provider_from_config()
    return _provider_name


def get_provider_name() -> str:
    _maybe_reload_provider_from_config()
    return _provider_name


def supported_provider_names() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDER_FACTORIES))


def get_feature_provider() -> FeatureDataProvider:
    return _feature_provider


def set_feature_provider(provider: FeatureDataProvider) -> None:
    global _feature_provider
    _feature_provider = provider


_sync_provider_from_config()
