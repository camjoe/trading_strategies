from types import SimpleNamespace

import pandas as pd
import pytest

import trading.services.auto_trading as auto_trading_service


def test_build_iv_rank_proxy_handles_empty_and_single() -> None:
    def fake_fetch_close_series(ticker: str, period: str):
        assert period == "1y"
        if ticker == "EMPTY":
            return None
        if ticker == "ONE":
            return pd.Series(range(1, 50), dtype=float)
        return None

    assert auto_trading_service.build_iv_rank_proxy(["EMPTY"], fetch_close_series_fn=fake_fetch_close_series) == {}
    assert auto_trading_service.build_iv_rank_proxy(["ONE"], fetch_close_series_fn=fake_fetch_close_series) == {"ONE": 50.0}


def test_validate_trade_count_range_and_account_names() -> None:
    with pytest.raises(ValueError, match="min-trades"):
        auto_trading_service.validate_trade_count_range(0, 1)
    with pytest.raises(ValueError, match="max-trades"):
        auto_trading_service.validate_trade_count_range(2, 1)

    assert auto_trading_service.resolve_account_names("acct1, acct2") == ["acct1", "acct2"]
    with pytest.raises(ValueError, match="No accounts"):
        auto_trading_service.resolve_account_names(" , ")


def test_resolve_market_inputs_and_run_accounts() -> None:
    universe, prices, iv_rank = auto_trading_service.resolve_market_inputs(
        "tickers.txt",
        load_tickers_from_file_fn=lambda _path: ["AAPL"],
        fetch_latest_prices_fn=lambda _universe: {"AAPL": 101.0},
        build_iv_rank_proxy_fn=lambda _universe: {"AAPL": 50.0},
    )
    assert universe == ["AAPL"]
    assert prices == {"AAPL": 101.0}
    assert iv_rank == {"AAPL": 50.0}

    results = auto_trading_service.run_accounts(
        conn=object(),
        account_names=["acct1", "acct2"],
        universe=universe,
        prices=prices,
        iv_rank_proxy=iv_rank,
        min_trades=1,
        max_trades=2,
        fee=0.0,
        run_for_account_fn=lambda **kwargs: 2 if kwargs["account_name"] == "acct1" else 1,
    )
    assert results == [("acct1", 2), ("acct2", 1)]


def test_parse_runtime_as_of_iso_handles_supported_formats() -> None:
    from common.time import parse_utc_iso

    naive = parse_utc_iso("2026-03-21T12:00:00")
    zulu = parse_utc_iso("2026-03-21T12:00:00Z")
    parsed = parse_utc_iso("2026-03-21T12:00:00+02:00")

    assert naive.isoformat().endswith("+00:00")
    assert zulu.isoformat().endswith("+00:00")
    assert parsed.isoformat().endswith("+00:00")
