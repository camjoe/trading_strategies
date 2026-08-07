from types import SimpleNamespace

import pandas as pd
import pytest

import trading.services.auto_trading as auto_trading_service
import trading.services.auto_trading.inputs as auto_trading_inputs
from tests.src.trading.services.auto_trading.factories import make_feature_fetchers
from tests.support.backtesting import bar_frame
from trading.models.accounts import AccountConfig
from trading.models.execution import AccountRunResult
from trading.services.accounts import create_account


def test_build_iv_rank_proxy_handles_empty_and_single() -> None:
    def fake_fetch_ohlcv(ticker: str, period: str, interval: str):
        assert period == "1y"
        assert interval == "1d"
        if ticker == "ONE":
            return bar_frame(pd.Series(range(1, 50), dtype=float))
        return None

    provider = SimpleNamespace(fetch_ohlcv=fake_fetch_ohlcv)

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


def test_resolve_market_inputs_and_run_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    bars = bar_frame(pd.Series(range(1, 50), dtype=float))
    monkeypatch.setattr(auto_trading_inputs, "fetch_latest_prices", lambda _universe, **_kwargs: {"AAPL": 101.0})
    monkeypatch.setattr(auto_trading_inputs, "fetch_bar_histories", lambda _universe, **_kwargs: {"AAPL": bars})
    monkeypatch.setattr(auto_trading_inputs, "build_iv_rank_proxy", lambda _universe, **_kwargs: {"AAPL": 50.0})

    universe, prices, iv_rank, histories = auto_trading_service.resolve_market_inputs(["AAPL"])
    assert universe == ["AAPL"]
    assert prices == {"AAPL": 101.0}
    assert iv_rank == {"AAPL": 50.0}
    assert list(histories) == ["AAPL"]

    def _fake_trade_loop(**kwargs):
        name = kwargs["account_name"]
        return AccountRunResult(account_name=name, submitted_count=2 if name == "acct1" else 1)

    monkeypatch.setattr(auto_trading_inputs, "_run_account_trade_loop", _fake_trade_loop)
    results = auto_trading_service.run_accounts(
        conn=object(),
        account_names=["acct1", "acct2"],
        universe=universe,
        prices=prices,
        iv_rank_proxy=iv_rank,
        max_trades=2,
        fee=0.0,
        broker_factory=lambda _: None,
        feature_fetchers=make_feature_fetchers(),
    )
    assert [(r.account_name, r.submitted_count) for r in results] == [("acct1", 2), ("acct2", 1)]
    assert all(not r.halted for r in results)


def test_resolve_run_universe_unions_the_books_own_universes(conn) -> None:
    """The fetch set must cover every symbol a book could select, not a fixed file."""
    create_account(conn, "acct_default", "trend", 5000.0, "SPY")
    create_account(conn, "acct_growth", "trend", 5000.0, "SPY", config=AccountConfig(trade_universes=["growth"]))

    universe = auto_trading_inputs.resolve_run_universe(conn, ["acct_default", "acct_growth"])

    default_only = auto_trading_inputs.resolve_run_universe(conn, ["acct_default"])
    growth_only = auto_trading_inputs.resolve_run_universe(conn, ["acct_growth"])

    assert set(universe) == set(default_only) | set(growth_only)
    # CRWD is growth-only: under the old fixed tickers file it was never priced,
    # so the growth book could not have traded it.
    assert "CRWD" in universe
    assert "CRWD" not in default_only
    assert len(universe) == len(set(universe))


def test_resolve_run_universe_raises_when_no_book_carries_symbols(conn) -> None:
    create_account(conn, "acct_none", "trend", 5000.0, "SPY")
    conn.execute("UPDATE books SET status = 'closed'")

    with pytest.raises(ValueError, match="carries any symbol"):
        auto_trading_inputs.resolve_run_universe(conn, ["acct_none"])


def test_resolve_market_inputs_raises_when_universe_is_empty() -> None:
    with pytest.raises(ValueError, match="Ticker universe is empty"):
        auto_trading_inputs.resolve_market_inputs([])


def test_resolve_market_inputs_raises_when_prices_are_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_trading_inputs, "fetch_latest_prices", lambda _universe, **_kwargs: {})

    with pytest.raises(ValueError, match="Could not fetch any prices"):
        auto_trading_inputs.resolve_market_inputs(["AAPL"])


def test_run_account_trade_loop_delegates_to_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    fake_runtime = types.ModuleType("trading.services.auto_trading.runtime")
    fake_runtime.run_for_account = lambda **kwargs: kwargs["max_trades"]  # type: ignore[attr-defined]
    import sys

    monkeypatch.setitem(sys.modules, "trading.services.auto_trading.runtime", fake_runtime)

    result = auto_trading_inputs._run_account_trade_loop(
        conn=object(),
        account_name="acct1",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=5,
        fee=0.0,
        broker_factory=lambda _: None,
        feature_fetchers=make_feature_fetchers(),
    )
    assert result == 5
    from common.time import parse_utc_iso

    naive = parse_utc_iso("2026-03-21T12:00:00")
    zulu = parse_utc_iso("2026-03-21T12:00:00Z")
    parsed = parse_utc_iso("2026-03-21T12:00:00+02:00")

    assert naive.isoformat().endswith("+00:00")
    assert zulu.isoformat().endswith("+00:00")
    assert parsed.isoformat().endswith("+00:00")
