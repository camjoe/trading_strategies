from types import SimpleNamespace

import pandas as pd
import pytest

import trading.services.auto_trading as auto_trading_service
import trading.services.auto_trading.inputs as auto_trading_inputs
from tests.src.trading.services.auto_trading.factories import make_feature_fetchers


def test_build_iv_rank_proxy_handles_empty_and_single() -> None:
    def fake_fetch_close_series(ticker: str, period: str):
        assert period == "1y"
        if ticker == "EMPTY":
            return None
        if ticker == "ONE":
            return pd.Series(range(1, 50), dtype=float)
        return None

    provider = SimpleNamespace(fetch_close_series=fake_fetch_close_series)

    assert auto_trading_service.build_iv_rank_proxy(["EMPTY"], provider=provider) == {}
    assert auto_trading_service.build_iv_rank_proxy(["ONE"], provider=provider) == {"ONE": 50.0}


def test_validate_trade_count_range_and_account_names() -> None:
    with pytest.raises(ValueError, match="min-trades"):
        auto_trading_service.validate_trade_count_range(0, 1)
    with pytest.raises(ValueError, match="max-trades"):
        auto_trading_service.validate_trade_count_range(2, 1)

    assert auto_trading_service.resolve_account_names("acct1, acct2") == ["acct1", "acct2"]
    with pytest.raises(ValueError, match="No accounts"):
        auto_trading_service.resolve_account_names(" , ")
    assert auto_trading_service.validate_execution_mode("ACCOUNT") == "account"
    assert auto_trading_service.validate_execution_mode("sleeve") == "sleeve"
    with pytest.raises(ValueError, match="execution_mode must be one of"):
        auto_trading_service.validate_execution_mode("invalid-mode")


def test_resolve_market_inputs_and_run_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_trading_inputs, "load_tickers_from_file", lambda _path: ["AAPL"])
    monkeypatch.setattr(auto_trading_inputs, "fetch_latest_prices", lambda _universe, **_kwargs: {"AAPL": 101.0})
    monkeypatch.setattr(auto_trading_inputs, "build_iv_rank_proxy", lambda _universe, **_kwargs: {"AAPL": 50.0})

    universe, prices, iv_rank = auto_trading_service.resolve_market_inputs("tickers.txt")
    assert universe == ["AAPL"]
    assert prices == {"AAPL": 101.0}
    assert iv_rank == {"AAPL": 50.0}

    seen_modes: list[str] = []

    def _fake_trade_loop(**kwargs):
        seen_modes.append(kwargs["execution_mode"])
        return 2 if kwargs["account_name"] == "acct1" else 1

    monkeypatch.setattr(auto_trading_inputs, "_run_account_trade_loop", _fake_trade_loop)
    results = auto_trading_service.run_accounts(
        conn=object(),
        account_names=["acct1", "acct2"],
        universe=universe,
        prices=prices,
        iv_rank_proxy=iv_rank,
        min_trades=1,
        max_trades=2,
        fee=0.0,
        execution_mode="sleeve",
        broker_factory=lambda _: None,
        feature_fetchers=make_feature_fetchers(),
    )
    assert results == [("acct1", 2), ("acct2", 1)]
    assert seen_modes == ["sleeve", "sleeve"]


def test_resolve_market_inputs_raises_when_universe_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_trading_inputs, "load_tickers_from_file", lambda _path: [])

    with pytest.raises(ValueError, match="Ticker universe is empty"):
        auto_trading_inputs.resolve_market_inputs("tickers.txt")


def test_resolve_market_inputs_raises_when_prices_are_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_trading_inputs, "load_tickers_from_file", lambda _path: ["AAPL"])
    monkeypatch.setattr(auto_trading_inputs, "fetch_latest_prices", lambda _universe, **_kwargs: {})

    with pytest.raises(ValueError, match="Could not fetch any prices"):
        auto_trading_inputs.resolve_market_inputs("tickers.txt")


def test_run_account_trade_loop_delegates_to_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    fake_runtime = types.ModuleType("trading.services.auto_trading.runtime")
    fake_runtime.run_for_account = lambda **kwargs: kwargs["min_trades"]  # type: ignore[attr-defined]
    import sys

    monkeypatch.setitem(sys.modules, "trading.services.auto_trading.runtime", fake_runtime)

    result = auto_trading_inputs._run_account_trade_loop(
        conn=object(),
        account_name="acct1",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=3,
        max_trades=5,
        fee=0.0,
        execution_mode="account",
        broker_factory=lambda _: None,
        feature_fetchers=make_feature_fetchers(),
    )
    assert result == 3
    from common.time import parse_utc_iso

    naive = parse_utc_iso("2026-03-21T12:00:00")
    zulu = parse_utc_iso("2026-03-21T12:00:00Z")
    parsed = parse_utc_iso("2026-03-21T12:00:00+02:00")

    assert naive.isoformat().endswith("+00:00")
    assert zulu.isoformat().endswith("+00:00")
    assert parsed.isoformat().endswith("+00:00")
