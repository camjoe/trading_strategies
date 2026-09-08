"""Provider routing: name resolution and concrete-adapter construction."""

from __future__ import annotations

import pytest

from infrastructure.market_data import DemoMarketDataProvider, YFinanceProvider, build_provider, resolve_provider_name


def test_default_provider_is_yfinance() -> None:
    assert resolve_provider_name() == "yfinance"
    assert isinstance(build_provider(), YFinanceProvider)


def test_env_var_selects_the_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_PROVIDER", "demo")

    assert resolve_provider_name() == "demo"
    assert isinstance(build_provider(), DemoMarketDataProvider)


def test_explicit_name_beats_the_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MARKET_DATA_PROVIDER", "demo")

    assert isinstance(build_provider("yfinance"), YFinanceProvider)


@pytest.mark.parametrize("name", ["DEMO", " demo ", "Demo"])
def test_provider_names_are_case_and_space_insensitive(name: str) -> None:
    assert isinstance(build_provider(name), DemoMarketDataProvider)


def test_unknown_provider_name_raises_and_lists_what_is_supported() -> None:
    with pytest.raises(ValueError, match="Unsupported market data provider") as excinfo:
        build_provider("not-a-real-provider")

    assert "demo" in str(excinfo.value)
    assert "yfinance" in str(excinfo.value)


def test_unknown_env_provider_fails_at_build_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bad config must stop the composition root, not a later fetch deep in a run."""
    monkeypatch.setenv("TRADING_MARKET_DATA_PROVIDER", "tiingo")

    with pytest.raises(ValueError, match="Unsupported market data provider"):
        build_provider()


def test_each_call_returns_a_fresh_instance() -> None:
    assert build_provider("demo") is not build_provider("demo")
