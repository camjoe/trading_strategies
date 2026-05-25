from __future__ import annotations

from collections.abc import Callable

import pytest

import trading.backtesting.backtest as backtest_module
from tests.support.backtesting import install_backtest_market_data


@pytest.fixture
def bt_market_data(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[str], list[float] | None], None]:
    """Factory that installs stub market data into the backtest module.

    Removes the need to import and pass ``backtest_module`` and ``monkeypatch``
    to ``install_backtest_market_data`` in every integration test.

    Usage::

        def test_foo(conn, bt_market_data):
            create_backtest_account(conn, "acct_foo")
            bt_market_data(["AAPL"])                              # default benchmark [100, 105]
            bt_market_data(["AAPL", "MSFT"], [100.0, 103.0])     # explicit benchmark
    """

    def _install(tickers: list[str], benchmark_values: list[float] | None = None) -> None:
        install_backtest_market_data(
            monkeypatch,
            backtest_module,
            tickers=tickers,
            benchmark_values=benchmark_values or [100.0, 105.0],
        )

    return _install
