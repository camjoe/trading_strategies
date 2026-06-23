"""Stateful market-data provider locator (legacy global).

This module keeps the process-wide ``get_provider()`` singleton + config
hot-reload behavior. It is being retired in favor of explicit dependency
injection via :mod:`trading.services.market_data.factory`; new code should call
``build_provider`` / ``build_feature_provider`` and inject the result rather than
reach for these globals.
"""

from __future__ import annotations

from pathlib import Path

from .factory import _DEFAULT_PROVIDER_NAME
from .factory import _config_path
from .factory import _provider_factory
from .factory import build_provider
from .factory import resolve_provider_name
from .factory import supported_provider_names as supported_provider_names
from .features import ProxyFeatureDataProvider
from .protocols import FeatureDataProvider
from .protocols import MarketDataProvider
from .providers import YFinanceProvider

_provider: MarketDataProvider = YFinanceProvider()
_provider_name = _DEFAULT_PROVIDER_NAME
_provider_source = "default"
_provider_config_mtime: float | None = None
_feature_provider: FeatureDataProvider = ProxyFeatureDataProvider()


def _config_mtime(config_path: Path) -> float | None:
    return config_path.stat().st_mtime if config_path.exists() else None


def _set_provider_state(provider: MarketDataProvider, *, name: str, source: str) -> None:
    global _provider, _provider_name, _provider_source
    _provider = provider
    _provider_name = name
    _provider_source = source


def _sync_provider_from_config() -> None:
    global _provider_config_mtime

    target_name = resolve_provider_name()
    _set_provider_state(build_provider(target_name), name=target_name, source="config")
    _provider_config_mtime = _config_mtime(_config_path())


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
    _provider_factory(key)
    _set_provider_state(build_provider(key), name=key, source="manual")


def reload_provider_from_config() -> str:
    _sync_provider_from_config()
    return _provider_name


def get_provider_name() -> str:
    _maybe_reload_provider_from_config()
    return _provider_name


def get_feature_provider() -> FeatureDataProvider:
    return _feature_provider


def set_feature_provider(provider: FeatureDataProvider) -> None:
    global _feature_provider
    _feature_provider = provider


_sync_provider_from_config()
